import json, datetime as dt
import time
from kafka import KafkaConsumer
import psycopg2
from loguru import logger
from maintenance_intelligence.cmms.adapter import create_cmms_adapter, submit_work_order_with_retry
from maintenance_intelligence.api.metrics import wo_drafts_total
from maintenance_intelligence.runner.config import Settings

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


def persist_work_order(conn, recommendation, result):
    workorder_created_at, handoff_completed_at, workorder_completed_at = _lifecycle_timestamps(result)
    metadata = {
        "source": f"agent-wo-bridge-{result.get('backend', 'unknown')}",
        "created_at": result.get("created_at", dt.datetime.utcnow().isoformat() + "Z"),
        "request": result.get("request"),
        "response": result.get("response"),
        "raw_response": result.get("raw_response"),
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
                    result.get("status", "DRAFT"),
                    recommendation.get("title"),
                    recommendation.get("rationale"),
                    recommendation.get("priority", "MEDIUM"),
                    json.dumps(metadata),
                    workorder_created_at,
                    handoff_completed_at,
                    workorder_completed_at,
                ),
            )


def process_recommendation(message_value, conn, adapter, retry_attempts: int = 3, retry_interval_s: float = 1.0, sleep_fn=time.sleep):
    recommendation = message_value.get("recommendation", {})
    result = submit_work_order_with_retry(
        adapter,
        recommendation,
        retry_attempts=retry_attempts,
        retry_interval_s=retry_interval_s,
        sleep_fn=sleep_fn,
    )
    if result.get("handoff_complete"):
        persist_work_order(conn, recommendation, result)
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
