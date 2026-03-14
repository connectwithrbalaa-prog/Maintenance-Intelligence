import os, json, time, uuid, threading, datetime as dt
from kafka import KafkaProducer, KafkaConsumer
import psycopg2

KAFKA = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
PG_DSN = "dbname={db} user={user} password={pwd} host={host} port=5432".format(
    db=os.getenv("POSTGRES_DB", "maintenance"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    pwd=os.getenv("POSTGRES_PASSWORD", "postgres"),
    host=os.getenv("POSTGRES_HOST", "timescaledb"),
)


def with_pg():
    while True:
        try:
            return psycopg2.connect(PG_DSN)
        except Exception:
            time.sleep(1)


def simulator():
    prod = KafkaProducer(bootstrap_servers=KAFKA, value_serializer=lambda v: json.dumps(v).encode("utf-8"))
    asset_ids = ["PUMP-101", "PUMP-102", "COMP-201"]
    print("[sim] ready")
    while True:
        for a in asset_ids:
            evt = {
                "event_type": "event.raised",
                "event_id": str(uuid.uuid4()),
                "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
                "org_id": "demo-org",
                "asset_id": a,
                "kind": "alarm",
                "severity": "high",
                "summary": f"High vibration on {a}",
                "details": {"rms": 9.2, "threshold": 7.5},
                "lineage": {"source": "simulator"},
            }
            prod.send("canonical.event.raised", evt)
            prod.flush()
            print("[sim] emitted alarm", evt["event_id"], a)
        time.sleep(2)


def ingestion():
    conn = with_pg()
    with conn:
        with conn.cursor() as cur:
            try:
                cur.execute(open("/workspace/scripts/db_init.sql").read())
            except Exception:
                pass
    cons = KafkaConsumer(
        "canonical.asset.upserted",
        "canonical.event.raised",
        bootstrap_servers=KAFKA,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-ingestion",
        auto_offset_reset="earliest",
    )
    print("[ingestion] ready")
    for msg in cons:
        evt = msg.value
        et = evt.get("event_type")
        if et == "event.raised":
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
            print(f"[ingestion] stored {et} id={evt.get('event_id')}")


def rca():
    cons = KafkaConsumer(
        "canonical.event.raised",
        bootstrap_servers=KAFKA,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-rca",
        auto_offset_reset="earliest",
    )
    prod = KafkaProducer(bootstrap_servers=KAFKA, value_serializer=lambda v: json.dumps(v).encode("utf-8"))
    print("[rca] ready")
    for msg in cons:
        evt = msg.value
        if evt.get("kind") not in ("alarm", "anomaly"):
            continue
        rec = {
            "event_type": "recommendation.created",
            "event_id": str(uuid.uuid4()),
            "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
            "org_id": evt.get("org_id"),
            "recommendation": {
                "id": str(uuid.uuid4()),
                "asset_id": evt.get("asset_id"),
                "title": f"Investigate {evt.get('kind')} on asset {evt.get('asset_id')}",
                "rationale": "Stub RCA — replace with GenAI Gateway output.",
                "evidence": [evt.get("event_id", "")],
                "model": {"name": "stub", "version": "0.0.1"},
                "immutable": True,
            },
            "lineage": {"source": "agent-rca-stub"},
        }
        prod.send("canonical.recommendation.created", rec)
        prod.flush()
        print("[rca] emitted recommendation", rec["recommendation"]["id"])


def wo_bridge():
    conn = with_pg()
    cons = KafkaConsumer(
        "canonical.recommendation.created",
        bootstrap_servers=KAFKA,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-wo-bridge",
        auto_offset_reset="earliest",
    )
    print("[wo-bridge] ready")
    for msg in cons:
        rec = msg.value.get("recommendation", {})
        wo_id = f"WO-{rec.get('id', '')[:8]}"
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
                        json.dumps({"source": "agent-wo-bridge-stub", "created_at": dt.datetime.utcnow().isoformat() + "Z"}),
                    ),
                )
        print("[wo-bridge] created draft WO", wo_id)


if __name__ == "__main__":
    threads = [
        threading.Thread(target=simulator, daemon=True),
        threading.Thread(target=ingestion, daemon=True),
        threading.Thread(target=rca, daemon=True),
        threading.Thread(target=wo_bridge, daemon=True),
    ]
    for t in threads:
        t.start()
    print("[runner] started all threads")
    while True:
        time.sleep(5)
