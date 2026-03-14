import os, json, uuid, datetime as dt
from kafka import KafkaConsumer, KafkaProducer
from loguru import logger
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.genai.gateway import GenAIGateway
from maintenance_intelligence.runner.summaries import write_run_summary

def rca_agent(kafka_bootstrap: str = None):
    settings = Settings()
    kafka_bootstrap = kafka_bootstrap or settings.kafka_bootstrap

    cons = KafkaConsumer(
        "canonical.event.raised",
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-rca",
        auto_offset_reset="earliest",
    )
    prod = KafkaProducer(bootstrap_servers=kafka_bootstrap,
                         value_serializer=lambda v: json.dumps(v).encode("utf-8"))

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        logger.warning({"event":"genai.missing_key","note":"OPENAI_API_KEY not set; using fallback text"})
        gateway = None
    else:
        gateway = GenAIGateway(api_key=openai_key, model=getattr(settings, "genai_model", "gpt-4.1"),
                               timeout_s=getattr(settings, "genai_timeout_s", 25))

    for msg in cons:
        evt = msg.value
        if evt.get("kind") not in ("alarm", "anomaly"):
            continue

        context = {"notes": "MVP context; extend with signals/WOs/docs"}

        if gateway:
            g = gateway.call_rca(evt, context)
            rationale = g.get("text", "No output")
            model_meta = {"name": "openai", "version": g.get("model_version"), "tokens": g.get("tokens"), "latency_ms": g.get("latency_ms")}
        else:
            rationale = "Stub RCA (no OPENAI_API_KEY). Replace with GenAI output once key is set."
            model_meta = {"name": "openai", "version": "unset", "tokens": None, "latency_ms": None}

        rec_id = str(uuid.uuid4())
        out = {
            "event_type": "recommendation.created",
            "event_id": str(uuid.uuid4()),
            "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
            "org_id": evt.get("org_id"),
            "recommendation": {
                "id": rec_id,
                "asset_id": evt.get("asset_id"),
                "title": f"Investigate {evt.get('kind')} on asset {evt.get('asset_id')}",
                "rationale": rationale,
                "evidence": [evt.get("event_id", "")],
                "model": model_meta,
                "immutable": True,
            },
            "lineage": {"source": "agent-rca-genai"},
        }
        prod.send("canonical.recommendation.created", out)
        prod.flush()

        run_id = out["event_id"]
        write_run_summary(getattr(settings, "run_summary_dir", "outputs"), run_id, {
            "run_id": run_id,
            "status": "ok",
            "recommendation_id": rec_id,
            "event_id": evt.get("event_id"),
            "model": model_meta,
        })

        logger.info({"event":"rca.recommendation.created","id":rec_id,"model":model_meta})
