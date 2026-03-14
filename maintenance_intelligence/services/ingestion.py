import json
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

def ingestion(kafka_bootstrap: str, pg_dsn: str):
    conn = with_pg(pg_dsn)
    # DB bootstrap converted to no-op (per instruction)
    cons = KafkaConsumer(
        "canonical.asset.upserted",
        "canonical.event.raised",
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-ingestion",
        auto_offset_reset="earliest",
    )
    for msg in cons:
        evt = msg.value
        if evt.get("event_type") == "event.raised":
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO events(event_id, occurred_at, org_id, asset_id, kind, severity, summary, details, lineage) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) "
                        "ON CONFLICT (event_id) DO NOTHING",
                        (
                            evt.get("event_id"), evt.get("occurred_at"), evt.get("org_id"),
                            evt.get("asset_id"), evt.get("kind"), evt.get("severity"),
                            evt.get("summary"), json.dumps(evt.get("details")), json.dumps(evt.get("lineage")),
                        ),
                    )
            logger.info({"event":"ingestion.stored","id":evt.get("event_id")})
