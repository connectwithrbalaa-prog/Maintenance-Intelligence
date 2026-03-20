import datetime as dt
import json
import os
import signal
import sys
import time
import uuid
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from loguru import logger
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.genai.gateway import GenAIGateway
from maintenance_intelligence.runner.summaries import write_run_summary
from maintenance_intelligence.context.assembler import get_event_context
from maintenance_intelligence.services.notifications import emit_notification
from maintenance_intelligence.services.repair_plan_service import create_repair_plan, add_part_to_plan
import backoff
from maintenance_intelligence.api.metrics import (
    recommendations_created_total,
    rca_duration_seconds,
    rca_runs_total,
)


EDGE_LOCAL_FALLBACK_VERSION = "edge-fallback-v1"

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
        acks='all',
        retries=3,
        retry_backoff_ms=1000
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


def _context_with_fallback(evt: dict, settings: Settings) -> dict:
    fleet_wide = getattr(settings, "rca_fleet_wide_context", True)
    try:
        return get_event_context(evt, settings, fleet_wide=fleet_wide)
    except TypeError:
        # Older tests and call sites stub the helper with a 2-arg lambda.
        return get_event_context(evt, settings)


def _deterministic_edge_structured(evt: dict, ctx: dict, reason: str | None = None) -> dict:
    asset_id = _as_trimmed_string(evt.get("asset_id")) or "unknown asset"
    event_kind = _as_trimmed_string(evt.get("kind")) or "event"
    event_summary = _as_trimmed_string(evt.get("summary")) or f"{event_kind.title()} detected"
    work_orders = _ordered_unique_strings(ctx.get("last_wo_titles") or [])
    doc_chunk_ids = _ordered_unique_strings([item.get("chunk_id") for item in ctx.get("doc_chunks", []) if isinstance(item, dict)])
    signal_ids = _ordered_unique_strings([item.get("signal_id") for item in ctx.get("recent_signals", []) if isinstance(item, dict)])
    evidence_ids = _ordered_unique_strings([evt.get("event_id")] + doc_chunk_ids + signal_ids)

    hypothesis = [f"{event_summary} on {asset_id} requires local inspection while GenAI analysis is unavailable."]
    if work_orders:
        hypothesis.append(f"Recent maintenance activity may be related: {work_orders[0]}.")

    root_causes = [
        "Observed asset condition deviates from the expected operating baseline.",
        "Manual review of local signals and maintenance context is required before remote GenAI analysis resumes.",
    ]
    if event_kind == "alarm":
        root_causes[0] = "A protection, alarm, or process threshold was exceeded under current operating conditions."

    contributing_factors = []
    if doc_chunk_ids:
        contributing_factors.append("Local maintenance documents were available for fallback review.")
    if signal_ids:
        contributing_factors.append("Recent signals were present and should be checked against the current condition.")
    if work_orders:
        contributing_factors.append("Recent work order history may have changed asset condition or maintenance state.")

    immediate_actions = [
        f"Inspect {asset_id} at the source of the reported {event_kind}.",
        "Verify the alert condition against the current operating state and instrumentation.",
    ]
    if work_orders:
        immediate_actions.append(f"Review recent work such as '{work_orders[0]}' before approving additional handoff.")

    pm_suggestions = [
        f"Schedule a manual follow-up inspection for {asset_id} in the next maintenance window.",
        "Capture technician findings so the remote RCA can be refined once GenAI connectivity returns.",
    ]
    if event_kind == "alarm":
        pm_suggestions.append("Confirm alarm thresholds and sensor health during the follow-up inspection.")

    summary_suffix = f" Reason: {reason}." if reason else ""
    return {
        "title": f"Local fallback RCA for {asset_id}",
        "summary": f"Deterministic edge fallback generated this RCA because GenAI was unavailable for {asset_id}.{summary_suffix}",
        "hypothesis": hypothesis,
        "root_causes": root_causes,
        "contributing_factors": contributing_factors,
        "evidence_ids": evidence_ids,
        "immediate_actions": immediate_actions,
        "pm_suggestions": pm_suggestions,
        "repair_plan": {
            "parts_list": [],
            "tools_required": [],
            "procedure_steps": [],
            "estimated_duration_hrs": 0.0,
            "safety_requirements": [],
            "permit_type": "",
            "spare_parts_cost_estimate": 0.0,
        },
        "confidence": 0.42,
    }


def _edge_local_fallback(evt: dict, ctx: dict, reason: str | None = None) -> tuple[dict, str, dict, str, str]:
    structured = _deterministic_edge_structured(evt, ctx, reason=reason)
    rationale = _build_rationale(structured, structured.get("summary", ""))
    model_meta = {
        "name": "local-deterministic",
        "version": EDGE_LOCAL_FALLBACK_VERSION,
        "tokens": None,
        "latency_ms": 0,
        "confidence": structured.get("confidence", 0.42),
    }
    return structured, rationale, model_meta, "agent-rca-edge-local-fallback", "local-deterministic"


def _genai_result_indicates_failure(result: dict) -> bool:
    text = result.get("text") if isinstance(result, dict) else None
    return isinstance(text, str) and text.startswith("[GENAI_ERROR]")


def _resolve_inference(evt: dict, settings: Settings, ctx: dict, gateway=None):
    if gateway is not None:
        try:
            result = gateway.call_rca(evt, ctx)
        except Exception as exc:
            if settings.edge_mode_enabled:
                return _edge_local_fallback(evt, ctx, reason=str(exc))
            raise
        if settings.edge_mode_enabled and _genai_result_indicates_failure(result):
            return _edge_local_fallback(evt, ctx, reason=result.get("text"))
        structured = result.get("structured") or {}
        rationale = _build_rationale(structured, result.get("text", "No output"))
        model_meta = {
            "name": "openai",
            "version": result.get("model_version"),
            "tokens": result.get("tokens"),
            "latency_ms": result.get("latency_ms"),
            "confidence": structured.get("confidence", 0.5),
        }
        return structured, rationale, model_meta, "agent-rca-genai", "genai"

    if settings.edge_mode_enabled:
        return _edge_local_fallback(evt, ctx, reason="OPENAI gateway unavailable")

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
    return structured, rationale, model_meta, "agent-rca-genai", "stub"


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


def _persist_repair_plan(settings: Settings, evt: dict, run_id: str, recommendation_id: str, structured: dict, rationale: str):
    repair_plan = structured.get("repair_plan") or {}
    if not _repair_plan_payload_has_content(repair_plan):
        return None

    summary_text = _as_trimmed_string(structured.get("summary")) or _as_trimmed_string(structured.get("title"))
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
            name=_as_trimmed_string(raw_part.get("part_no")) or _as_trimmed_string(raw_part.get("description")),
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
    ctx = _context_with_fallback(evt, settings)
    structured, rationale, model_meta, lineage_source, inference_mode = _resolve_inference(evt, settings, ctx, gateway=gateway)

    rec_id = str(uuid.uuid4())
    doc_chunk_ids = [d.get("chunk_id") for d in ctx.get("doc_chunks", []) if isinstance(d, dict)]
    signal_ids = [s.get("signal_id") for s in ctx.get("recent_signals", []) if isinstance(s, dict) and s.get("signal_id")]

    out = {
        "event_type": "recommendation.created",
        "event_id": str(uuid.uuid4()),
        "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "org_id": evt.get("org_id"),
        "recommendation": {
            "id": rec_id,
            "asset_id": evt.get("asset_id"),
            "title": (structured.get("title") or f"Investigate {evt.get('kind')} on asset {evt.get('asset_id')}"),
            "rationale": rationale,
            "repair_plan": structured.get("repair_plan") or {},
            "evidence": _ordered_unique_strings(
                [evt.get("event_id")] + doc_chunk_ids + signal_ids + (structured.get("evidence_ids") or [])
            ),
            "model": model_meta,
            "immutable": True,
        },
        "lineage": {"source": lineage_source},
        "context_meta": {
            "org_id": evt.get("org_id"),
            "asset_id": evt.get("asset_id"),
            "event_kind": evt.get("kind"),
            "event_summary": evt.get("summary"),
            "wo_titles_count": len(ctx.get("last_wo_titles", [])),
            "doc_chunk_ids": doc_chunk_ids,
            "signal_ids": signal_ids,
            "context_scope": ctx.get("context_scope", "local"),
            "fleet_external_ref_count": (ctx.get("fleet_context_summary") or {}).get("external_ref_count", 0),
            "fleet_referenced_asset_ids": (ctx.get("fleet_context_summary") or {}).get("referenced_asset_ids", []),
            "inference_mode": inference_mode,
            "degraded_inference": inference_mode == "local-deterministic",
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

    try:
        emit_notification(
            event_type="rca.completed",
            severity="info",
            summary=f"RCA run completed for asset {evt.get('asset_id') or 'unknown'}",
            org_id=evt.get("org_id"),
            site_id=evt.get("site_id"),
            dedupe_key=f"rca-completed:{run_id}",
            payload={
                "run_id": run_id,
                "recommendation_id": rec_id,
                "event_id": evt.get("event_id"),
                "asset_id": evt.get("asset_id"),
                "inference_mode": inference_mode,
                "context_scope": ctx.get("context_scope", "local"),
            },
            settings=settings,
        )
    except Exception:
        pass

    logger.info({"event": "rca.recommendation.created", "id": rec_id, "model": model_meta, "ctx": out.get("context_meta")})
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
        gateway = GenAIGateway(api_key=openai_key, model=getattr(settings, "genai_model", "gpt-4.1"),
                               timeout_s=getattr(settings, "genai_timeout_s", 25)) if openai_key else None

        for msg in cons:
            if shutdown_requested:
                break

            evt = msg.value

            try:
                process_event(evt, settings, prod, gateway=gateway)

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
