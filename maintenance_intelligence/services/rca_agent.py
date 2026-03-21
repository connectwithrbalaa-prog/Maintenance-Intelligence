import os
import json
import uuid
import datetime as dt
import signal
import sys
import time
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from loguru import logger
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.genai.gateway import GenAIGateway
from maintenance_intelligence.runner.summaries import write_run_summary
from maintenance_intelligence.context.assembler import get_event_context
from maintenance_intelligence.services.repair_plan_service import (
    create_repair_plan,
    add_part_to_plan,
)
import backoff
from maintenance_intelligence.api.metrics import (
    recommendations_created_total,
    rca_runs_total,
    rca_duration_seconds,
)


@backoff.on_exception(backoff.expo, KafkaError, max_tries=5, max_time=60)
def create_kafka_consumer(kafka_bootstrap: str):
    """Create Kafka consumer with retry logic."""
    return KafkaConsumer(
        "canonical.event.raised",
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
        acks="all",
        retries=3,
        retry_backoff_ms=1000,
    )


@backoff.on_exception(backoff.expo, KafkaError, max_tries=3, max_time=30)
def send_recommendation(producer, recommendation):
    """Send recommendation with retry logic."""
    producer.send("canonical.recommendation.created", recommendation)
    producer.flush()


def _ordered_unique_strings(values):
    seen = set()
    ordered = []
    for value in values:
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _build_rationale(structured: dict, fallback_text: str) -> str:
    hypotheses = structured.get("hypothesis") or []
    if isinstance(hypotheses, list) and hypotheses:
        return "\n".join(hypotheses[:4])

    root_causes = structured.get("root_causes") or []
    if isinstance(root_causes, list) and root_causes:
        return "\n".join(root_causes[:4])

    summary = structured.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()

    return fallback_text


def _as_trimmed_string(value):
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None


def _repair_plan_payload_has_content(repair_plan: dict) -> bool:
    if not isinstance(repair_plan, dict):
        return False
    keys_with_values = (
        "parts_list",
        "tools_required",
        "procedure_steps",
        "estimated_duration_hrs",
        "safety_requirements",
        "permit_type",
        "spare_parts_cost_estimate",
    )
    for key in keys_with_values:
        value = repair_plan.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, (int, float)) and value not in (0, 0.0):
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _persist_repair_plan(
    settings: Settings,
    evt: dict,
    run_id: str,
    recommendation_id: str,
    structured: dict,
    rationale: str,
):
    repair_plan = structured.get("repair_plan") or {}
    if not _repair_plan_payload_has_content(repair_plan):
        return None

    summary_text = _as_trimmed_string(structured.get("summary")) or _as_trimmed_string(
        structured.get("title")
    )
    plan = create_repair_plan(
        settings.pg_dsn,
        run_id=run_id,
        recommendation_id=recommendation_id,
        org_id=evt.get("org_id"),
        asset_id=evt.get("asset_id"),
        summary=summary_text,
        rationale=rationale,
        confidence=structured.get("confidence"),
    )

    for raw_part in repair_plan.get("parts_list") or []:
        if not isinstance(raw_part, dict):
            continue
        add_part_to_plan(
            settings.pg_dsn,
            plan["plan_id"],
            name=_as_trimmed_string(raw_part.get("part_no"))
            or _as_trimmed_string(raw_part.get("description")),
            description=_as_trimmed_string(raw_part.get("description")),
            quantity=raw_part.get("qty"),
            unit=None,
            metadata={
                "part_no": raw_part.get("part_no"),
                "lead_time_days": raw_part.get("lead_time_days"),
            },
        )

    return plan


def process_event(evt: dict, settings: Settings, producer, gateway=None):
    if evt.get("kind") not in ("alarm", "anomaly"):
        return None

    _t0 = time.time()
    ctx = get_event_context(
        evt, settings, fleet_wide=getattr(settings, "rca_fleet_wide_context", True)
    )

    if gateway:
        g = gateway.call_rca(evt, ctx)
        structured = g.get("structured") or {}
        rationale = _build_rationale(structured, g.get("text", "No output"))
        model_meta = {
            "name": "openai",
            "version": g.get("model_version"),
            "tokens": g.get("tokens"),
            "latency_ms": g.get("latency_ms"),
            "confidence": structured.get("confidence", 0.5),
        }
    else:
        rationale = "Stub RCA (no OPENAI_API_KEY). Replace with GenAI output once key is set."
        structured = {
            "title": "RCA Draft",
            "hypothesis": [rationale],
            "evidence_ids": [],
            "immediate_actions": [],
            "pm_suggestions": [],
            "confidence": 0.3,
        }
        model_meta = {
            "name": "openai",
            "version": "unset",
            "tokens": None,
            "latency_ms": None,
            "confidence": structured.get("confidence", 0.3),
        }

    rec_id = str(uuid.uuid4())
    doc_chunk_ids = [d.get("chunk_id") for d in ctx.get("doc_chunks", []) if isinstance(d, dict)]
    signal_ids = [
        s.get("signal_id")
        for s in ctx.get("recent_signals", [])
        if isinstance(s, dict) and s.get("signal_id")
    ]

    out = {
        "event_type": "recommendation.created",
        "event_id": str(uuid.uuid4()),
        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "org_id": evt.get("org_id"),
        "recommendation": {
            "id": rec_id,
            "asset_id": evt.get("asset_id"),
            "title": (
                structured.get("title")
                or f"Investigate {evt.get('kind')} on asset {evt.get('asset_id')}"
            ),
            "rationale": rationale,
            "repair_plan": structured.get("repair_plan") or {},
            "evidence": _ordered_unique_strings(
                [evt.get("event_id")]
                + doc_chunk_ids
                + signal_ids
                + (structured.get("evidence_ids") or [])
            ),
            "model": model_meta,
            "immutable": True,
        },
        "lineage": {"source": "agent-rca-genai"},
        "context_meta": {
            "org_id": evt.get("org_id"),
            "asset_id": evt.get("asset_id"),
            "event_kind": evt.get("kind"),
            "event_summary": evt.get("summary"),
            "wo_titles_count": len(ctx.get("last_wo_titles", [])),
            "doc_chunk_ids": doc_chunk_ids,
            "signal_ids": signal_ids,
            "context_scope": ctx.get("context_scope", "local"),
            "fleet_external_ref_count": (ctx.get("fleet_context_summary") or {}).get(
                "external_ref_count", 0
            ),
            "fleet_referenced_asset_ids": (ctx.get("fleet_context_summary") or {}).get(
                "referenced_asset_ids", []
            ),
        },
    }

    send_recommendation(producer, out)

    run_id = out["event_id"]
    persisted_plan = None
    try:
        persisted_plan = _persist_repair_plan(settings, evt, run_id, rec_id, structured, rationale)
    except Exception as exc:
        logger.warning(
            {
                "event": "rca.repair_plan.persistence_failed",
                "run_id": run_id,
                "recommendation_id": rec_id,
                "error": str(exc),
            }
        )

    if persisted_plan is not None:
        out["recommendation"]["repair_plan"] = {
            **(structured.get("repair_plan") or {}),
            "plan_id": persisted_plan["plan_id"],
        }

    summary_payload = {
        "run_id": run_id,
        "status": "ok",
        "recommendation_id": rec_id,
        "event_id": evt.get("event_id"),
        "model": model_meta,
        "structured": structured,
        "context_meta": out.get("context_meta", {}),
        "context_scope": ctx.get("context_scope", "local"),
        "fleet_context_summary": ctx.get("fleet_context_summary", {}),
        "context_items": {"doc_chunks": ctx.get("doc_chunks", [])},
    }
    if persisted_plan is not None:
        summary_payload["repair_plan_id"] = persisted_plan["plan_id"]
    write_run_summary(getattr(settings, "run_summary_dir", "outputs"), run_id, summary_payload)

    logger.info(
        {
            "event": "rca.recommendation.created",
            "id": rec_id,
            "model": model_meta,
            "ctx": out.get("context_meta"),
        }
    )
    try:
        rca_runs_total.labels(service="rca_agent").inc()
        rca_duration_seconds.labels(service="rca_agent").observe(max(0.0, time.time() - _t0))
        recommendations_created_total.labels(service="rca_agent").inc()
    except Exception:
        pass

    return {
        "recommendation_event": out,
        "summary": summary_payload,
        "context": ctx,
    }


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
    kafka_bootstrap = kafka_bootstrap or settings.kafka_bootstrap

    cons = None
    prod = None

    try:
        cons = create_kafka_consumer(kafka_bootstrap)
        prod = create_kafka_producer(kafka_bootstrap)

        openai_key = os.getenv("OPENAI_API_KEY")
        gateway = (
            GenAIGateway(
                api_key=openai_key,
                model=getattr(settings, "genai_model", "gpt-4.1"),
                timeout_s=getattr(settings, "genai_timeout_s", 25),
            )
            if openai_key
            else None
        )

        for msg in cons:
            if shutdown_requested:
                break

            evt = msg.value

            try:
                process_event(evt, settings, prod, gateway=gateway)

            except Exception as e:
                logger.error(
                    {
                        "event": "rca_agent.processing_error",
                        "event_id": evt.get("event_id"),
                        "error": str(e),
                    }
                )
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
