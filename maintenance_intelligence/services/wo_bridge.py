import json, datetime as dt
import backoff
from kafka import KafkaConsumer
import psycopg2
from loguru import logger
from maintenance_intelligence.cmms.adapter import CMMSUnavailableError, create_cmms_adapter, normalize_work_order_result
from maintenance_intelligence.api.metrics import wo_drafts_total
from maintenance_intelligence.runner.config import Settings

def with_pg(dsn: str):
    import time
    while True:
        try:
            return psycopg2.connect(dsn)
        except Exception:
            time.sleep(1)


@backoff.on_exception(backoff.expo, CMMSUnavailableError, max_tries=3, max_time=30)
def submit_work_order(adapter, recommendation):
    return adapter.create_work_order(recommendation)


def persist_work_order(conn, recommendation, result):
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
                "INSERT INTO workorders (wo_id, asset_id, status, title, description, priority, metadata) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) "
                "ON CONFLICT (wo_id) DO NOTHING",
                (
                    result.get("wo_id"),
                    recommendation.get("asset_id"),
                    result.get("status", "DRAFT"),
                    recommendation.get("title"),
                    recommendation.get("rationale"),
                    recommendation.get("priority", "MEDIUM"),
                    json.dumps(metadata),
                ),
            )


def process_recommendation(message_value, conn, adapter):
    recommendation = message_value.get("recommendation", {})
    result = normalize_work_order_result(
        submit_work_order(adapter, recommendation),
        recommendation=recommendation,
        backend_name=getattr(adapter, "backend_name", None),
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
            process_recommendation(msg.value, conn, adapter)
    finally:
        try:
            cons.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
