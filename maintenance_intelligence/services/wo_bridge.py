import json, datetime as dt
import time
from kafka import KafkaConsumer
import psycopg2
from loguru import logger
from maintenance_intelligence.cmms.adapter import TERMINAL_WORK_ORDER_STATUSES, create_cmms_adapter, submit_work_order_with_retry
from maintenance_intelligence.api.metrics import wo_drafts_total
from maintenance_intelligence.runner.config import Settings


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _as_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


REGRESSIVE_WORK_ORDER_STATUSES = {"PENDING", "QUEUED", "DRAFT", "NEW"}

def with_pg(dsn: str):
    import time
    while True:
        try:
            return psycopg2.connect(dsn)
        except Exception:
            time.sleep(1)


def _lifecycle_timestamps(result):
    response = result.get("response") if isinstance(result.get("response"), dict) else {}
    raw_response = result.get("raw_response") if isinstance(result.get("raw_response"), dict) else {}
    workorder_created_at = (
        result.get("workorder_created_at")
        or result.get("created_at")
        or response.get("workorder_created_at")
        or response.get("created_at")
        or raw_response.get("workorder_created_at")
        or raw_response.get("created_at")
    )
    handoff_completed_at = (
        result.get("handoff_completed_at")
        or response.get("handoff_completed_at")
        or raw_response.get("handoff_completed_at")
        or response.get("statusdate")
        or response.get("changedate")
        or raw_response.get("statusdate")
        or raw_response.get("changedate")
        or (workorder_created_at if result.get("handoff_complete") else None)
    )
    workorder_completed_at = (
        result.get("workorder_completed_at")
        or response.get("workorder_completed_at")
        or response.get("actfinish")
        or response.get("completed_at")
        or response.get("closed_at")
        or response.get("finishdate")
        or raw_response.get("workorder_completed_at")
        or raw_response.get("actfinish")
        or raw_response.get("completed_at")
        or raw_response.get("closed_at")
        or raw_response.get("finishdate")
    )
    return workorder_created_at, handoff_completed_at, workorder_completed_at


def _status_upper(status):
    value = _as_text(status)
    return value.upper() if value else None


def _is_terminal_status(status):
    return _status_upper(status) in TERMINAL_WORK_ORDER_STATUSES


def _lifecycle_phase(status, handoff_completed_at, workorder_completed_at):
    if workorder_completed_at or _is_terminal_status(status):
        return "completed"
    if handoff_completed_at:
        return "handoff-complete"
    if _status_upper(status) in REGRESSIVE_WORK_ORDER_STATUSES:
        return "created"
    if status:
        return "active"
    return "pending"


def _merged_status(existing_status, next_status, existing_handoff_completed_at, next_handoff_completed_at, existing_completed_at, next_completed_at):
    existing_upper = _status_upper(existing_status)
    next_upper = _status_upper(next_status)
    if existing_completed_at and not next_completed_at and not _is_terminal_status(next_upper):
        return existing_status or existing_upper or next_status or "DRAFT"
    if _is_terminal_status(existing_upper) and not _is_terminal_status(next_upper) and not next_completed_at:
        return existing_status or existing_upper or next_status or "DRAFT"
    if existing_handoff_completed_at and not next_handoff_completed_at and next_upper in REGRESSIVE_WORK_ORDER_STATUSES:
        return existing_status or existing_upper or next_status or "DRAFT"
    return next_status or existing_status or "DRAFT"


def _existing_work_order_row(conn, wo_id):
    if not wo_id:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, workorder_created_at, handoff_completed_at, workorder_completed_at, metadata FROM workorders WHERE wo_id = %s",
            (wo_id,),
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {
        "status": row[0],
        "workorder_created_at": row[1],
        "handoff_completed_at": row[2],
        "workorder_completed_at": row[3],
        "metadata": row[4] if isinstance(row[4], dict) else {},
    }


def _handoff_metadata(recommendation, result, handoff_context=None):
    context = _as_dict(handoff_context)
    attempts = result.get("_attempts") if isinstance(result.get("_attempts"), list) else []
    last_attempt = attempts[-1] if attempts else {}
    workorder_created_at, handoff_completed_at, workorder_completed_at = _lifecycle_timestamps(result)
    return {
        "proposal_id": _as_text(context.get("proposal_id")),
        "recommendation_id": _as_text(context.get("recommendation_id")) or _as_text(recommendation.get("id")),
        "approved_by": _as_text(context.get("approved_by")),
        "origin": _as_text(context.get("origin")) or "bridge",
        "handoff_state": "success" if result.get("handoff_complete") else "pending",
        "attempt_count": len(attempts),
        "last_attempt": last_attempt if isinstance(last_attempt, dict) else {},
        "wo_id": _as_text(result.get("wo_id")),
        "backend": _as_text(result.get("backend")) or "unknown",
        "workorder_created_at": workorder_created_at,
        "handoff_completed_at": handoff_completed_at,
        "workorder_completed_at": workorder_completed_at,
    }


def persist_work_order(conn, recommendation, result, handoff_context=None):
    existing = _existing_work_order_row(conn, result.get("wo_id"))
    workorder_created_at, handoff_completed_at, workorder_completed_at = _lifecycle_timestamps(result)
    merged_workorder_created_at = existing.get("workorder_created_at") or workorder_created_at
    merged_handoff_completed_at = existing.get("handoff_completed_at") or handoff_completed_at
    merged_workorder_completed_at = existing.get("workorder_completed_at") or workorder_completed_at
    merged_status = _merged_status(
        existing.get("status"),
        result.get("status", "DRAFT"),
        existing.get("handoff_completed_at"),
        handoff_completed_at,
        existing.get("workorder_completed_at"),
        workorder_completed_at,
    )
    metadata = {
        "source": f"agent-wo-bridge-{result.get('backend', 'unknown')}",
        "created_at": result.get("created_at", dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")),
        "request": result.get("request"),
        "response": result.get("response"),
        "raw_response": result.get("raw_response"),
        "handoff": _handoff_metadata(recommendation, result, handoff_context=handoff_context),
    }
    existing_metadata = _as_dict(existing.get("metadata"))
    metadata = {**existing_metadata, **metadata}
    metadata["handoff"] = {
        **_as_dict(existing_metadata.get("handoff")),
        **_as_dict(metadata.get("handoff")),
        "status_before": _as_text(existing.get("status")),
        "status_after": _as_text(merged_status),
        "lifecycle_phase": _lifecycle_phase(
            merged_status,
            merged_handoff_completed_at,
            merged_workorder_completed_at,
        ),
    }
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO workorders (wo_id, asset_id, status, title, description, priority, metadata, workorder_created_at, handoff_completed_at, workorder_completed_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) "
                "ON CONFLICT (wo_id) DO UPDATE SET "
                "asset_id = COALESCE(workorders.asset_id, EXCLUDED.asset_id), "
                "status = COALESCE(EXCLUDED.status, workorders.status), "
                "title = COALESCE(workorders.title, EXCLUDED.title), "
                "description = COALESCE(workorders.description, EXCLUDED.description), "
                "priority = COALESCE(workorders.priority, EXCLUDED.priority), "
                "metadata = COALESCE(workorders.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb), "
                "workorder_created_at = COALESCE(workorders.workorder_created_at, EXCLUDED.workorder_created_at), "
                "handoff_completed_at = COALESCE(workorders.handoff_completed_at, EXCLUDED.handoff_completed_at), "
                "workorder_completed_at = COALESCE(workorders.workorder_completed_at, EXCLUDED.workorder_completed_at)",
                (
                    result.get("wo_id"),
                    recommendation.get("asset_id"),
                    merged_status,
                    recommendation.get("title"),
                    recommendation.get("rationale"),
                    recommendation.get("priority", "MEDIUM"),
                    json.dumps(metadata),
                    merged_workorder_created_at,
                    merged_handoff_completed_at,
                    merged_workorder_completed_at,
                ),
            )


def process_recommendation(message_value, conn, adapter, retry_attempts: int = 3, retry_interval_s: float = 1.0, sleep_fn=time.sleep):
    recommendation = message_value.get("recommendation", {})
    handoff_context = _as_dict(message_value.get("handoff_context"))
    result = submit_work_order_with_retry(
        adapter,
        recommendation,
        retry_attempts=retry_attempts,
        retry_interval_s=retry_interval_s,
        sleep_fn=sleep_fn,
    )
    if result.get("handoff_complete"):
        persist_work_order(conn, recommendation, result, handoff_context=handoff_context)
        logger.info({"event": "wo_bridge.draft_created", "wo_id": result.get("wo_id"), "backend": result.get("backend")})
        wo_drafts_total.labels(service="wo_bridge").inc()
    else:
        logger.warning({"event": "wo_bridge.handoff_pending", "recommendation_id": recommendation.get("id"), "backend": result.get("backend")})
    return result

def wo_bridge(kafka_bootstrap: str, pg_dsn: str, settings: Settings | None = None, connection_factory=with_pg, consumer_factory=KafkaConsumer, adapter_factory=create_cmms_adapter):
    settings = settings or Settings()
    conn = connection_factory(pg_dsn)
    adapter = adapter_factory(settings)
    cons = consumer_factory(
        "canonical.recommendation.created",
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-wo-bridge",
        auto_offset_reset="earliest",
    )
    try:
        for msg in cons:
            process_recommendation(
                msg.value,
                conn,
                adapter,
                retry_attempts=settings.pm_handoff_retry_attempts,
                retry_interval_s=settings.pm_handoff_retry_interval_s,
            )
    finally:
        try:
            cons.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
