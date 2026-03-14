import time, uuid, json, datetime as dt
from kafka import KafkaProducer

def simulator(kafka_bootstrap: str):
    prod = KafkaProducer(bootstrap_servers=kafka_bootstrap,
                         value_serializer=lambda v: json.dumps(v).encode("utf-8"))
    asset_ids = ["PUMP-101", "PUMP-102", "COMP-201"]
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
        time.sleep(2)
