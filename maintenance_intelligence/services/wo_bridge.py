import datetime as dt
import json
import time
from kafka import KafkaConsumer
import psycopg2
from loguru import logger
from maintenance_intelligence.cmms.adapter import (
    CMMSAdapterError,
    CMMSPayloadError,
    cmms_failure_summary_from_error,
    create_cmms_adapter,
    is_terminal_work_order_status,
    normalize_cmms_failure_summary,
    normalize_work_order_lifecycle,
    submit_work_order_with_retry,
    work_order_lifecycle_phase,
)
from maintenance_intelligence.api.metrics import wo_drafts_total
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.edge_command_buffer import EdgeCommandBuffer


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
QUEUED_OFFLINE_STATUS = "queued-offline"


def with_pg(dsn: str, retry_interval_s: float = 1.0, max_attempts: int = 30):
    """Open a PostgreSQL connection with bounded retries.

    A finite retry budget prevents API handlers from hanging forever when the
    database is unavailable.
    """
    last_error = None
    for attempt in range(max_attempts):
        try:
            return psycopg2.connect(dsn)
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                break
            time.sleep(retry_interval_s)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to connect to PostgreSQL")


def _status_upper(status):
    value = _as_text(status)
    return value.upper() if value else None


def _merged_status(
    existing_status,
    next_status,
    existing_handoff_completed_at,
    next_handoff_completed_at,
    existing_completed_at,
    next_completed_at,
):
    existing_upper = _status_upper(existing_status)
    next_upper = _status_upper(next_status)
    if (
        existing_completed_at
        and not next_completed_at
        and not is_terminal_work_order_status(next_upper)
    ):
        return existing_status or existing_upper or next_status or "DRAFT"
    if (
        is_terminal_work_order_status(existing_upper)
        and not is_terminal_work_order_status(next_upper)
        and not next_completed_at
    ):
        return existing_status or existing_upper or next_status or "DRAFT"
    if (
        existing_handoff_completed_at
        and not next_handoff_completed_at
        and next_upper in REGRESSIVE_WORK_ORDER_STATUSES
    ):
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


def _existing_proposal_row(conn, proposal_id):
    if not proposal_id:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, approved_by, work_order_id, metadata FROM pm_proposals WHERE proposal_id = %s",
            (proposal_id,),
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {
        "status": row[0],
        "approved_by": row[1],
        "work_order_id": row[2],
        "metadata": row[3] if isinstance(row[3], dict) else {},
    }


def _attempt_entry(
    result=None, *, handoff_state="pending", approved_by=None, origin="bridge", error_message=None
):
    attempted_at = dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "attempt_number": None,
        "attempted_at": attempted_at,
        "approved_by": approved_by,
        "approved_at": attempted_at if handoff_state == "success" else None,
        "handoff_state": handoff_state,
        "origin": origin,
        "result": (
            "success" if handoff_state == "success" else ("failure" if error_message else "pending")
        ),
        "connector_result": result if isinstance(result, dict) else {},
        "error_message": error_message or "",
        "failure_summary": normalize_cmms_failure_summary(
            detail=error_message, handoff_state=handoff_state
        ),
    }


def _approval_attempts(metadata):
    if not isinstance(metadata, dict):
        return []
    attempts = metadata.get("approval_attempts")
    if isinstance(attempts, list):
        return [item for item in attempts if isinstance(item, dict)]
    approval = metadata.get("approval")
    return [approval] if isinstance(approval, dict) else []


def _proposal_metadata_with_attempt(
    existing_metadata, attempt, *, approved_by=None, handoff_state="pending"
):
    metadata = existing_metadata if isinstance(existing_metadata, dict) else {}
    attempts = list(_approval_attempts(metadata))
    attempt_number = len(attempts) + 1
    normalized_attempt = {
        **attempt,
        "attempt_number": attempt_number,
        "approved_by": approved_by or attempt.get("approved_by"),
    }
    approval = {
        "approved_by": normalized_attempt.get("approved_by"),
        "approved_at": normalized_attempt.get("approved_at"),
        "attempted_at": normalized_attempt.get("attempted_at"),
        "handoff_state": handoff_state,
        "origin": normalized_attempt.get("origin") or "bridge",
        "result": (
            normalized_attempt.get("connector_result")
            if isinstance(normalized_attempt.get("connector_result"), dict)
            else {}
        ),
        "detail": normalized_attempt.get("error_message") or None,
        "failure_summary": normalize_cmms_failure_summary(
            normalized_attempt.get("failure_summary"),
            detail=normalized_attempt.get("error_message"),
            handoff_state=handoff_state,
        ),
    }
    return {
        **metadata,
        "approval": approval,
        "approval_attempts": [*attempts, normalized_attempt],
    }


def update_proposal_handoff_status(
    conn, proposal_id, result=None, *, approved_by=None, origin="bridge", error_message=None
):
    existing = _existing_proposal_row(conn, proposal_id)
    if not existing:
        return {}
    if error_message:
        status = existing.get("status") or QUEUED_OFFLINE_STATUS
        handoff_state = QUEUED_OFFLINE_STATUS
        work_order_id = existing.get("work_order_id")
        attempt = _attempt_entry(
            None,
            handoff_state=handoff_state,
            approved_by=approved_by or existing.get("approved_by"),
            origin=origin,
            error_message=error_message,
        )
    else:
        handoff_complete = bool(result and result.get("handoff_complete"))
        status = "approved" if handoff_complete else "pending"
        handoff_state = "success" if handoff_complete else "pending"
        work_order_id = (
            result.get("wo_id") if isinstance(result, dict) else existing.get("work_order_id")
        )
        attempt = _attempt_entry(
            result,
            handoff_state=handoff_state,
            approved_by=approved_by or existing.get("approved_by"),
            origin=origin,
        )
    metadata = _proposal_metadata_with_attempt(
        existing.get("metadata"),
        attempt,
        approved_by=approved_by or existing.get("approved_by"),
        handoff_state=handoff_state,
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pm_proposals SET status = %s, approved_by = %s, work_order_id = %s, metadata = %s::jsonb WHERE proposal_id = %s",
                (
                    status,
                    approved_by or existing.get("approved_by"),
                    work_order_id,
                    json.dumps(metadata),
                    proposal_id,
                ),
            )
    return {"status": status, "work_order_id": work_order_id, "metadata": metadata}


def _handoff_metadata(recommendation, result, handoff_context=None):
    context = _as_dict(handoff_context)
    attempts = result.get("_attempts") if isinstance(result.get("_attempts"), list) else []
    last_attempt = attempts[-1] if attempts else {}
    lifecycle = normalize_work_order_lifecycle(result)
    return {
        "proposal_id": _as_text(context.get("proposal_id")),
        "recommendation_id": _as_text(context.get("recommendation_id"))
        or _as_text(recommendation.get("id")),
        "approved_by": _as_text(context.get("approved_by")),
        "origin": _as_text(context.get("origin")) or "bridge",
        "handoff_state": "success" if result.get("handoff_complete") else "pending",
        "attempt_count": len(attempts),
        "last_attempt": last_attempt if isinstance(last_attempt, dict) else {},
        "wo_id": _as_text(result.get("wo_id")),
        "backend": _as_text(result.get("backend")) or "unknown",
        "workorder_created_at": lifecycle.get("workorder_created_at"),
        "handoff_completed_at": lifecycle.get("handoff_completed_at"),
        "workorder_completed_at": lifecycle.get("workorder_completed_at"),
        "lifecycle_phase": lifecycle.get("phase") or "pending",
        "terminal_state": bool(lifecycle.get("terminal")),
        "lifecycle": lifecycle,
    }


def persist_work_order(conn, recommendation, result, handoff_context=None):
    existing = _existing_work_order_row(conn, result.get("wo_id"))
    lifecycle = normalize_work_order_lifecycle(result)
    workorder_created_at = lifecycle.get("workorder_created_at")
    handoff_completed_at = lifecycle.get("handoff_completed_at")
    workorder_completed_at = lifecycle.get("workorder_completed_at")
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
        "created_at": result.get(
            "created_at", dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "request": result.get("request"),
        "response": result.get("response"),
        "raw_response": result.get("raw_response"),
        "handoff": _handoff_metadata(recommendation, result, handoff_context=handoff_context),
    }
    existing_metadata = _as_dict(existing.get("metadata"))
    metadata = {**existing_metadata, **metadata}
    merged_lifecycle_phase = work_order_lifecycle_phase(
        merged_status,
        merged_handoff_completed_at,
        merged_workorder_completed_at,
        workorder_created_at=merged_workorder_created_at,
        handoff_complete=bool(
            result.get("wo_id") or merged_workorder_created_at or merged_handoff_completed_at
        ),
    )
    metadata["handoff"] = {
        **_as_dict(existing_metadata.get("handoff")),
        **_as_dict(metadata.get("handoff")),
        "status_before": _as_text(existing.get("status")),
        "status_after": _as_text(merged_status),
        "lifecycle_phase": merged_lifecycle_phase,
        "terminal_state": bool(
            merged_workorder_completed_at or is_terminal_work_order_status(merged_status)
        ),
        "lifecycle": {
            **_as_dict(_as_dict(metadata.get("handoff")).get("lifecycle")),
            "status": _as_text(merged_status) or "PENDING",
            "status_upper": _status_upper(merged_status) or "PENDING",
            "handoff_complete": bool(
                result.get("wo_id") or merged_workorder_created_at or merged_handoff_completed_at
            ),
            "workorder_created_at": merged_workorder_created_at,
            "handoff_completed_at": merged_handoff_completed_at,
            "workorder_completed_at": merged_workorder_completed_at,
            "terminal": bool(
                merged_workorder_completed_at or is_terminal_work_order_status(merged_status)
            ),
            "phase": merged_lifecycle_phase,
        },
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


def process_recommendation(
    message_value,
    conn,
    adapter,
    retry_attempts: int = 3,
    retry_interval_s: float = 1.0,
    sleep_fn=time.sleep,
):
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
        logger.info(
            {
                "event": "wo_bridge.draft_created",
                "wo_id": result.get("wo_id"),
                "backend": result.get("backend"),
            }
        )
        wo_drafts_total.labels(service="wo_bridge").inc()
    else:
        logger.warning(
            {
                "event": "wo_bridge.handoff_pending",
                "recommendation_id": recommendation.get("id"),
                "backend": result.get("backend"),
            }
        )
    return result


def _replay_edge_command_queue(
    conn,
    adapter,
    queue: EdgeCommandBuffer,
    *,
    batch_size: int = 25,
    retry_attempts: int = 1,
    retry_interval_s: float = 0.0,
):
    replayed_total = 0
    queue.mark_replay_attempt_started()
    for command in queue.list_queued_commands(limit=batch_size):
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        proposal_id = _as_text(command.get("proposal_id"))
        try:
            result = process_recommendation(
                payload,
                conn,
                adapter,
                retry_attempts=retry_attempts,
                retry_interval_s=retry_interval_s,
            )
            if proposal_id:
                context = _as_dict(payload.get("handoff_context"))
                update_proposal_handoff_status(
                    conn,
                    proposal_id,
                    result,
                    approved_by=_as_text(context.get("approved_by")),
                    origin="edge-replay",
                )
            queue.record_replay_success(proposal_id or "")
            replayed_total += 1
        except (CMMSAdapterError, CMMSPayloadError) as exc:
            queue.record_replay_failure(proposal_id or "", str(exc))
            if proposal_id:
                context = _as_dict(payload.get("handoff_context"))
                update_proposal_handoff_status(
                    conn,
                    proposal_id,
                    None,
                    approved_by=_as_text(context.get("approved_by")),
                    origin="edge-replay",
                    error_message=cmms_failure_summary_from_error(exc).get("message") or str(exc),
                )
            return {"replayed": replayed_total, "error": str(exc)}
    return {"replayed": replayed_total, "error": None}


def wo_bridge(
    kafka_bootstrap: str,
    pg_dsn: str,
    settings: Settings | None = None,
    connection_factory=with_pg,
    consumer_factory=KafkaConsumer,
    adapter_factory=create_cmms_adapter,
):
    settings = settings or Settings()
    conn = connection_factory(pg_dsn)
    adapter = adapter_factory(settings)
    command_queue = (
        EdgeCommandBuffer(settings.edge_command_buffer_path) if settings.edge_mode_enabled else None
    )
    cons = consumer_factory(
        "canonical.recommendation.created",
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-wo-bridge",
        auto_offset_reset="earliest",
    )
    try:
        for msg in cons:
            if command_queue and command_queue.queued_command_count() > 0:
                replay_outcome = _replay_edge_command_queue(
                    conn,
                    adapter,
                    command_queue,
                    batch_size=settings.edge_replay_batch_size,
                    retry_attempts=1,
                    retry_interval_s=0.0,
                )
                if replay_outcome.get("replayed"):
                    logger.info(
                        {
                            "event": "wo_bridge.edge_replayed",
                            "count": replay_outcome.get("replayed"),
                        }
                    )
                if replay_outcome.get("error"):
                    logger.warning(
                        {
                            "event": "wo_bridge.edge_replay_failed",
                            "error": replay_outcome.get("error"),
                        }
                    )
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
