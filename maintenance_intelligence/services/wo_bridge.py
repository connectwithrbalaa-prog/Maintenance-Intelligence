import json, datetime as dt
from kafka import KafkaConsumer
import psycopg2
from loguru import logger

def with_pg(dsn: str):
    import time
    while True:
        try:
            return psycopg2.connect(dsn)
        except Exception:
            time.sleep(1)

def wo_bridge(kafka_bootstrap: str, pg_dsn: str):
    conn = with_pg(pg_dsn)
    cons = KafkaConsumer(
        "canonical.recommendation.created",
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-wo-bridge",
        auto_offset_reset="earliest",
    )
    for msg in cons:
        rec = msg.value.get("recommendation", {})
        wo_id = f"WO-{rec.get('id','')[:8]}"
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO workorders (wo_id, asset_id, status, title, description, priority, metadata) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) "
                    "ON CONFLICT (wo_id) DO NOTHING",
                    (
                        wo_id,
                        rec.get("asset_id"),
                        "DRAFT",
                        rec.get("title"),
                        rec.get("rationale"),
                        "MEDIUM",
                        json.dumps({"source":"agent-wo-bridge-stub","created_at": dt.datetime.utcnow().isoformat() + "Z"}),
                    ),
                )
        logger.info({"event":"wo_bridge.draft_created","wo_id":wo_id})
