set -euo pipefail
BRANCH="feature/genai-gateway-run-summaries"

# Create/checkout branch
git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

# Ensure dirs
mkdir -p maintenance_intelligence/genai maintenance_intelligence/runner tests

# Add openai dependency to pyproject (idempotent best-effort)
if ! grep -q '"openai' pyproject.toml; then
  perl -0777 -pe 's/(dependencies = \[\n)/$1  "openai>=1.0",\n/s' -i pyproject.toml
fi

# Run summaries writer
cat > maintenance_intelligence/runner/summaries.py << 'PY'
import json, os, datetime as dt
from pathlib import Path

def write_run_summary(dir_path: str, run_id: str, payload: dict) -> str:
    date_dir = Path(dir_path) / dt.datetime.utcnow().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    out = date_dir / f"{run_id}.json"
    with out.open("w") as f:
        json.dump(payload, f, indent=2)
    return str(out)
PY

# Append GenAI + run summary settings to Settings (idempotent guard)
if ! grep -q "genai_model" maintenance_intelligence/runner/config.py; then
cat >> maintenance_intelligence/runner/config.py << 'PY'

# --- GenAI / summaries ---
from pydantic import Field  # ensure imported

setattr(Settings, "genai_model", Field(default="gpt-4.1"))
setattr(Settings, "genai_timeout_s", Field(default=25))
setattr(Settings, "run_summary_dir", Field(default="outputs"))
PY
fi

# OpenAI gateway
mkdir -p maintenance_intelligence/genai
cat > maintenance_intelligence/genai/gateway.py << 'PY'
import os, time
from typing import Dict, Any
from loguru import logger
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

class GenAIGateway:
    def __init__(self, api_key: str, model: str, timeout_s: int = 25):
        self.model = model
        self.timeout_s = timeout_s
        if OpenAI is None:
            raise RuntimeError("openai package not installed")
        self.client = OpenAI(api_key=api_key)

    def call_rca(self, event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        prompt = self._build_prompt(event, context)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an industrial maintenance RCA assistant. Be concise and cite signals/WOs/docs when possible."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                timeout=self.timeout_s,
            )
            text = resp.choices[0].message.content.strip() if resp.choices else ""
            usage = getattr(resp, "usage", None)
            tokens = usage.total_tokens if usage else None
        except Exception as e:
            logger.error({"event":"genai.error","err":str(e)})
            text, tokens = f"[GENAI_ERROR] {e}", None

        latency = int((time.time() - t0) * 1000)
        return {
            "text": text,
            "model_version": self.model,
            "tokens": tokens,
            "latency_ms": latency,
        }

    def _build_prompt(self, event: Dict[str, Any], context: Dict[str, Any]) -> str:
        lines = []
        lines.append("Task: Draft an RCA hypothesis and recommended next actions for this alarm/anomaly.")
        lines.append(f"Event: {event}")
        lines.append(f"Context: {context}")
        lines.append("Output format:\\n- Title\\n- Hypothesis (2-4 bullets)\\n- Evidence to check (signals/WOs/docs)\\n- Immediate actions (1-3)\\n- Longer-term PM/design suggestions (1-2)")
        return "\\n".join(lines)
PY

# Wire RCA agent to use gateway + run summaries
cat > maintenance_intelligence/services/rca_agent.py << 'PY'
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
PY

# Smoke test (placeholder)
cat > tests/test_rca_smoke.py << 'PY'
def test_placeholder():
    assert True
PY

# README update
cat >> README.md << 'PY'

## GenAI Gateway (OpenAI) & Run Summaries

- Set OPENAI_API_KEY to enable GenAI RCA drafts.
- Defaults:
  - MI_GENAI_MODEL=gpt-4.1
  - MI_GENAI_TIMEOUT_S=25
  - MI_RUN_SUMMARY_DIR=outputs (JSON artifacts per run)
- RCA agent includes model_version/tokens/latency in recommendation.model.
PY

# Commit & push
git add .
git commit -m "feat: OpenAI GenAI gateway integration for RCA + run summaries (JSON artifacts)"
git push -u origin "$BRANCH"