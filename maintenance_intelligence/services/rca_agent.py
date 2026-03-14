import json, uuid, datetime as dt
from kafka import KafkaConsumer, KafkaProducer
from loguru import logger

def rca_agent(kafka_bootstrap: str):
    cons = KafkaConsumer(
        "canonical.event.raised",
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-rca",
        auto_offset_reset="earliest",
    )
    prod = KafkaProducer(bootstrap_servers=kafka_bootstrap,
                         value_serializer=lambda v: json.dumps(v).encode("utf-8"))
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
        logger.info({"event":"rca.recommendation.created","id":rec["recommendation"]["id"]})
