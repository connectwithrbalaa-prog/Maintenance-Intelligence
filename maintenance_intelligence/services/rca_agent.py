import os, json, uuid, datetime as dt
from kafka import KafkaConsumer, KafkaProducer
from loguru import logger
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.genai.gateway import GenAIGateway
from maintenance_intelligence.runner.summaries import write_run_summary
from maintenance_intelligence.context.assembler import get_event_context

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
    gateway = GenAIGateway(api_key=openai_key, model=getattr(settings, "genai_model", "gpt-4.1"),
                           timeout_s=getattr(settings, "genai_timeout_s", 25)) if openai_key else None

    for msg in cons:
        evt = msg.value
        if evt.get("kind") not in ("alarm", "anomaly"):
            continue

        # Assemble MVP context
        ctx = get_event_context(evt, settings)

        if gateway:
            g = gateway.call_rca(evt, ctx)
            structured = g.get("structured") or {}
            rationale = "
".join(structured.get("hypothesis", [])[:4]) or g.get("text", "No output")
            model_meta = {"name": "openai", "version": g.get("model_version"), "tokens": g.get("tokens"), "latency_ms": g.get("latency_ms"), "confidence": structured.get("confidence", 0.5)}
        else:
            structured = {"title":"RCA Draft","hypothesis":[rationale],"evidence_ids":[],"immediate_actions":[],"pm_suggestions":[],"confidence":0.3}
            rationale = rationale
            model_meta = {"name": "openai", "version": "unset", "tokens": None, "latency_ms": None, "confidence": structured.get("confidence", 0.3)}

        rec_id = str(uuid.uuid4())
        doc_chunk_ids = [d.get("chunk_id") for d in ctx.get("doc_chunks", []) if isinstance(d, dict)]

        out = {
            "event_type": "recommendation.created",
            "event_id": str(uuid.uuid4()),
            "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
            "org_id": evt.get("org_id"),
            "recommendation": {
                "id": rec_id,
                "asset_id": evt.get("asset_id"),
                "title": (structured.get("title") or f"Investigate {evt.get('kind')} on asset {evt.get('asset_id')}"),
                "rationale": rationale,
                "evidence": [evt.get("event_id", "")] + list(set(doc_chunk_ids + (structured.get("evidence_ids") or []))),
                "model": model_meta,
                "immutable": True,
            },
            "lineage": {"source": "agent-rca-genai"},
            "context_meta": {
                "wo_titles_count": len(ctx.get("last_wo_titles", [])),
                "doc_chunk_ids": doc_chunk_ids,
            },
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
            "context_meta": out.get("context_meta", {}),
        })

        logger.info({"event":"rca.recommendation.created","id":rec_id,"model":model_meta,"ctx":out.get("context_meta")})
