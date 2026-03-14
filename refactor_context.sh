set -euo pipefail
BRANCH="feature/context-assembly-rag"

git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

# New context assembler
mkdir -p maintenance_intelligence/context
cat > maintenance_intelligence/context/assembler.py << 'PY'
import datetime as dt
from typing import Dict, Any, List, Optional
import psycopg2
from loguru import logger
from maintenance_intelligence.runner.config import Settings

def with_pg(dsn: str):
    import time
    while True:
        try:
            return psycopg2.connect(dsn)
        except Exception:
            time.sleep(1)

def get_event_context(event: Dict[str, Any], settings: Optional[Settings] = None) -> Dict[str, Any]:
    """
    MVP bootstrap context assembly.
    - last_wo_titles: last few WOs for the asset (90d)
    - signal_summary: stub (placeholder)
    - doc_chunks: stub (assumes optional doc_chunks table later)
    Returns empty lists gracefully if tables not present.
    """
    settings = settings or Settings()
    asset_id = event.get("asset_id")
    out: Dict[str, Any] = {"asset_id": asset_id, "last_wo_titles": [], "signal_summary": {}, "doc_chunks": []}
    conn = None
    try:
        conn = with_pg(settings.pg_dsn)
        # last few WOs (if table exists)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT title FROM workorders
                    WHERE asset_id = %s AND (NOW() - INTERVAL '90 days') < NOW()
                    ORDER BY RANDOM() LIMIT 5
                    """, (asset_id,)
                )
                rows = cur.fetchall()
                out["last_wo_titles"] = [r[0] for r in rows if r and r[0]]
        except Exception as e:
            logger.debug({"event":"ctx.wo.skip","err":str(e)})

        # signal summary stub (extend via real signals later)
        out["signal_summary"] = {"note": "MVP stub; add rolling means/min/max from measurements"}

        # doc chunks stub (if doc_chunks table exists)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT chunk_id, title FROM doc_chunks
                    WHERE asset_id = %s
                    ORDER BY RANDOM()
                    LIMIT 3
                    """, (asset_id,)
                )
                rows = cur.fetchall()
                out["doc_chunks"] = [{"chunk_id": r[0], "title": r[1]} for r in rows if r]
        except Exception as e:
            logger.debug({"event":"ctx.docs.skip","err":str(e)})

    except Exception as e:
        logger.debug({"event":"ctx.error","err":str(e)})
    finally:
        try:
            if conn: conn.close()
        except Exception:
            pass
    return out
PY

# Update RCA agent to use context assembler (keep GenAI integration)
cat > maintenance_intelligence/services/rca_agent.py << 'PY'
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
            rationale = g.get("text", "No output")
            model_meta = {"name": "openai", "version": g.get("model_version"), "tokens": g.get("tokens"), "latency_ms": g.get("latency_ms")}
        else:
            rationale = "Stub RCA (no OPENAI_API_KEY). Replace with GenAI output once key is set."
            model_meta = {"name": "openai", "version": "unset", "tokens": None, "latency_ms": None}

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
                "title": f"Investigate {evt.get('kind')} on asset {evt.get('asset_id')}",
                "rationale": rationale,
                "evidence": [evt.get("event_id", "")] + doc_chunk_ids,
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
PY

# Health endpoint
cat > maintenance_intelligence/api/health.py << 'PY'
from fastapi import APIRouter
from maintenance_intelligence.runner.config import Settings
import socket

router = APIRouter()

@router.get("/healthz")
def healthz():
    # Basic process-level health; deeper checks can be added (Kafka/PG pings)
    return {"status": "ok", "host": socket.gethostname()}
PY

# Mount health router in API (append import & include_router if not already present)
if ! grep -q "healthz" maintenance_intelligence/api/main.py; then
  sed -i '1i from maintenance_intelligence.api.health import router as health_router' maintenance_intelligence/api/main.py
  sed -i 's/app = FastAPI.*/&\\napp.include_router(health_router)/' maintenance_intelligence/api/main.py
fi

# Test (basic)
cat > tests/test_context_smoke.py << 'PY'
from maintenance_intelligence.context.assembler import get_event_context
def test_context_smoke():
    evt = {"asset_id":"TEST-ASSET","kind":"alarm"}
    ctx = get_event_context(evt)
    assert "asset_id" in ctx
PY

# Commit & push
git add .
git commit -m "feat: context assembly (MVP) + RAG bootstrap stubs + /healthz"
git push -u origin "$BRANCH"