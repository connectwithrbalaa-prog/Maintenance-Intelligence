import datetime as dt
import json
import os
import signal
import sys
import uuid

import backoff
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from loguru import logger

from maintenance_intelligence.api.metrics import (
    publish_budget_caps,
    rca_cost_usd_total,
    rca_duration_seconds,
    rca_latency_seconds,
    rca_runs_by_prompt_total,
    rca_runs_total,
    recommendations_created_total,
)
from maintenance_intelligence.context.assembler import get_event_context
from maintenance_intelligence.genai.gateway import GenAIGateway
from maintenance_intelligence.multitenancy import consumer_topics, event_in_scope, scoped_topic
from maintenance_intelligence.prompts.catalog import resolve_prompt_for_route
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.summaries import write_run_summary


@backoff.on_exception(backoff.expo, KafkaError, max_tries=5, max_time=60)
def create_kafka_consumer(kafka_bootstrap: str, settings: Settings):
    """Create Kafka consumer with retry logic."""
    return KafkaConsumer(
        *consumer_topics(["canonical.event.raised"], settings, org_id=settings.default_org),
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-rca",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        auto_commit_interval_ms=5000,
    )

@backoff.on_exception(backoff.expo, KafkaError, max_tries=5, max_time=60)
def create_kafka_producer(kafka_bootstrap: str):
    """Create Kafka producer with retry logic."""
    return KafkaProducer(
        bootstrap_servers=kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks='all',
        retries=3,
        retry_backoff_ms=1000
    )

@backoff.on_exception(backoff.expo, KafkaError, max_tries=3, max_time=30)
def send_recommendation(producer, recommendation, settings: Settings):
    """Send recommendation with retry logic."""
    producer.send(scoped_topic("canonical.recommendation.created", settings, recommendation.get("org_id")), recommendation)
    producer.flush()


def _resolve_model_rate(model_name: str | None, settings: Settings) -> float:
    model_name = model_name or "unset"
    configured_rates = settings.rca_model_rates
    if model_name in configured_rates:
        return configured_rates[model_name]
    for configured_model, rate in configured_rates.items():
        if model_name.startswith(configured_model):
            return rate
    return configured_rates.get("default", 0.0)


def _estimate_cost_usd(tokens: int | None, model_name: str | None, settings: Settings) -> float:
    if not tokens or tokens <= 0:
        return 0.0
    estimated = (float(tokens) / 1000.0) * _resolve_model_rate(model_name, settings)
    return round(max(0.0, estimated), 6)


def _record_prompt_run_metrics(
    prompt_id: str,
    variant: str,
    model_name: str,
    latency_ms: int | None,
    estimated_cost_usd: float,
    route_name: str = "rca",
    service: str = "rca_agent",
):
    prompt_label = prompt_id or "unknown"
    model_label = model_name or "unknown"
    rca_runs_total.labels(service=service).inc()
    rca_runs_by_prompt_total.labels(service=service, route=route_name, prompt_id=prompt_label, variant=variant).inc()
    if latency_ms is not None:
        rca_latency_seconds.labels(service=service, model=model_label, prompt_id=prompt_label).observe(max(0.0, latency_ms / 1000.0))
    if estimated_cost_usd > 0:
        rca_cost_usd_total.labels(model=model_label, prompt_id=prompt_label).inc(estimated_cost_usd)

def rca_agent(kafka_bootstrap: str = None):
    logger.info({"event": "rca_agent.start"})

    # Graceful shutdown handling
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        logger.info({"event": "rca_agent.shutdown_requested", "signal": signum})
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    settings = Settings()
    publish_budget_caps(settings.rca_budget_caps_usd)
    kafka_bootstrap = kafka_bootstrap or settings.kafka_bootstrap

    cons = None
    prod = None

    try:
        cons = create_kafka_consumer(kafka_bootstrap, settings)
        prod = create_kafka_producer(kafka_bootstrap)

        openai_key = os.getenv("OPENAI_API_KEY")
        gateway = GenAIGateway(api_key=openai_key, model=getattr(settings, "genai_model", "gpt-4.1"),
                               timeout_s=getattr(settings, "genai_timeout_s", 25)) if openai_key else None

        for msg in cons:
            if shutdown_requested:
                break

            evt = msg.value
            if not event_in_scope(evt.get("org_id"), settings, org_id=settings.default_org):
                continue
            if evt.get("kind") not in ("alarm", "anomaly"):
                continue

            import time
            _t0 = time.time()

            try:
                # Assemble MVP context
                ctx = get_event_context(evt, settings, org_id=evt.get("org_id"))
                prompt_selection = resolve_prompt_for_route(
                    route_name="rca",
                    org_id=evt.get("org_id") or settings.default_org,
                    subject_key=evt.get("event_id") or evt.get("asset_id") or str(uuid.uuid4()),
                    settings=settings,
                )
                prompt_meta = {
                    "prompt_id": prompt_selection["prompt_id"],
                    "variant": prompt_selection["variant"],
                    "route_name": prompt_selection["route_name"],
                    "auto_rollback_triggered": prompt_selection.get("auto_rollback_triggered", False),
                }

                if gateway:
                    try:
                        g = gateway.call_rca(evt, ctx, prompt_selection=prompt_selection["prompt"])
                    except TypeError:
                        g = gateway.call_rca(evt, ctx)
                    structured = g.get("structured") or {}
                    rationale = "\n".join(structured.get("hypothesis", [])[:4]) or g.get("text", "No output")
                    estimated_cost_usd = _estimate_cost_usd(g.get("tokens"), g.get("model_version"), settings)
                    model_meta = {
                        "name": "openai",
                        "version": g.get("model_version"),
                        "tokens": g.get("tokens"),
                        "latency_ms": g.get("latency_ms"),
                        "estimated_cost_usd": estimated_cost_usd,
                        "confidence": structured.get("confidence", 0.5),
                        "prompt_id": prompt_meta["prompt_id"],
                        "prompt_variant": prompt_meta["variant"],
                        "prompt_route": prompt_meta["route_name"],
                    }
                else:
                    rationale = "Stub RCA (no OPENAI_API_KEY). Replace with GenAI output once key is set."
                    structured = {"title":"RCA Draft","hypothesis":[rationale],"evidence_ids":[],"immediate_actions":[],"pm_suggestions":[],"confidence":0.3}
                    estimated_cost_usd = 0.0
                    model_meta = {
                        "name": "openai",
                        "version": "unset",
                        "tokens": None,
                        "latency_ms": None,
                        "estimated_cost_usd": estimated_cost_usd,
                        "confidence": structured.get("confidence", 0.3),
                        "prompt_id": prompt_meta["prompt_id"],
                        "prompt_variant": prompt_meta["variant"],
                        "prompt_route": prompt_meta["route_name"],
                    }

                rec_id = str(uuid.uuid4())
                doc_chunk_ids = [d.get("chunk_id") for d in ctx.get("doc_chunks", []) if isinstance(d, dict)]
                signal_ids = [s.get("signal_id") for s in ctx.get("recent_signals", []) if isinstance(s, dict) and s.get("signal_id")]

                out = {
                    "event_type": "recommendation.created",
                    "event_id": str(uuid.uuid4()),
                    "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
                    "org_id": evt.get("org_id"),
                    "recommendation": {
                        "id": rec_id,
                        "asset_id": evt.get("asset_id"),
                        "title": (structured.get("title") or f"Investigate {evt.get('kind')} on asset {evt.get('asset_id')}"),
                        "rationale": rationale,
                        "evidence": [evt.get("event_id", "")] + list(set(doc_chunk_ids + signal_ids + (structured.get("evidence_ids") or []))),
                        "model": model_meta,
                        "immutable": True,
                    },
                    "lineage": {"source": "agent-rca-genai"},
                    "context_meta": {
                        "wo_titles_count": len(ctx.get("last_wo_titles", [])),
                        "doc_chunk_ids": doc_chunk_ids,
                    },
                    "prompt": prompt_meta,
                }

                send_recommendation(prod, out, settings)

                run_id = out["event_id"]
                write_run_summary(getattr(settings, "run_summary_dir", "outputs"), run_id, {
                    "run_id": run_id,
                    "status": "ok",
                    "recommendation_id": rec_id,
                    "event_id": evt.get("event_id"),
                    "model": model_meta,
                    "prompt": prompt_meta,
                    "structured": structured,
                    "metrics": {
                        "estimated_cost_usd": estimated_cost_usd,
                        "latency_ms": model_meta.get("latency_ms"),
                        "tokens": model_meta.get("tokens"),
                    },
                    "context_meta": out.get("context_meta", {}),
                })

                logger.info({"event":"rca.recommendation.created","id":rec_id,"model":model_meta,"ctx":out.get("context_meta")})
                try:
                    _record_prompt_run_metrics(
                        prompt_meta["prompt_id"],
                        prompt_meta["variant"],
                        model_meta.get("version") or "unset",
                        model_meta.get("latency_ms"),
                        estimated_cost_usd,
                        route_name=prompt_meta["route_name"],
                    )
                    rca_duration_seconds.labels(service="rca_agent").observe(max(0.0, time.time() - _t0))
                    recommendations_created_total.labels(service="rca_agent").inc()
                except Exception:
                    pass

            except Exception as e:
                logger.error({"event": "rca_agent.processing_error", "event_id": evt.get("event_id"), "error": str(e)})
                # Continue processing other events

    except Exception as e:
        logger.error({"event": "rca_agent.error", "error": str(e)})
        sys.exit(1)
    finally:
        logger.info({"event": "rca_agent.shutting_down"})
        if cons:
            cons.close()
        if prod:
            prod.close(timeout=10)
        logger.info({"event": "rca_agent.stopped"})

    logger.info({"event": "rca_agent.exit"})
