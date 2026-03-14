set -euo pipefail
BRANCH="feature/rca-runner-orchestrator"

# Create/checkout branch
git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

# Dirs
mkdir -p maintenance_intelligence/runner maintenance_intelligence/services maintenance_intelligence/api maintenance_intelligence/models .github/workflows configs tests

# pyproject.toml (adds FastAPI, Typer, pydantic-settings, kafka, psycopg2)
cat > pyproject.toml << 'PY'
[project]
name = "maintenance-intelligence"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "typer>=0.12",
  "pydantic>=2.6",
  "pydantic-settings>=2.2",
  "httpx>=0.27",
  "loguru>=0.7",
  "python-json-logger>=2.0",
  "kafka-python>=2.0.2",
  "psycopg2-binary>=2.9",
]
[project.optional-dependencies]
dev = ["ruff>=0.3","black>=24.2","mypy>=1.8","pytest>=8.0","pytest-cov>=4.1"]
[project.scripts]
mi-runner = "maintenance_intelligence.runner.cli:app"
[tool.black]
line-length = 100
[tool.ruff]
line-length = 100
select = ["E","F","I","UP"]
PY

# Settings + logging
cat > maintenance_intelligence/runner/config.py << 'PY'
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    env: str = Field(default="dev")
    log_level: str = Field(default="INFO")
    kafka_bootstrap: str = Field(default="kafka:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    pg_db: str = Field(default="maintenance", alias="POSTGRES_DB")
    pg_user: str = Field(default="postgres", alias="POSTGRES_USER")
    pg_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    pg_host: str = Field(default="timescaledb", alias="POSTGRES_HOST")

    @property
    def pg_dsn(self) -> str:
        return f"dbname={self.pg_db} user={self.pg_user} password={self.pg_password} host={self.pg_host} port=5432"

    class Config:
        env_prefix = "MI_"
        extra = "allow"
PY

cat > maintenance_intelligence/runner/logging.py << 'PY'
from loguru import logger
import sys, time, uuid

def setup_logger(level: str = "INFO"):
    logger.remove()
    logger.add(sys.stdout, level=level, serialize=False)

def run_id() -> str:
    return str(uuid.uuid4())

def timed(fn):
    def _wrap(*a, **k):
        t0 = time.time()
        try:
            return fn(*a, **k)
        finally:
            logger.info({"event":"timing","fn":fn.__name__,"ms":int((time.time()-t0)*1000)})
    return _wrap
PY

# Orchestrator (single-shot)
cat > maintenance_intelligence/runner/core.py << 'PY'
from .config import Settings
from .logging import setup_logger, run_id, timed
from loguru import logger

@timed
def run(event_id: str, settings: Settings):
    setup_logger(settings.log_level)
    rid = run_id()
    logger.bind(run_id=rid).info({"event":"runner.start","event_id":event_id})
    rec_id = f"rec-{rid[:8]}"
    logger.info({"event":"recommendation.stub","id":rec_id,"note":"Kafka pipeline handles real flow"})
    return {"run_id": rid, "status": "ok", "recommendation_id": rec_id}
PY

# CLI
cat > maintenance_intelligence/runner/cli.py << 'PY'
import typer, json
from .config import Settings
from .core import run

app = typer.Typer(help="Maintenance Intelligence Runner CLI")

@app.command()
def rca(event_id: str):
    s = Settings()
    result = run(event_id, s)
    typer.echo(json.dumps(result))

if __name__ == "__main__":
    app()
PY

# Services split from runner.py (DB bootstrap -> no-op)
cat > maintenance_intelligence/services/simulator.py << 'PY'
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
PY

cat > maintenance_intelligence/services/ingestion.py << 'PY'
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
PY

cat > maintenance_intelligence/services/rca_agent.py << 'PY'
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
PY

cat > maintenance_intelligence/services/wo_bridge.py << 'PY'
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
PY

# Minimal API
cat > maintenance_intelligence/api/main.py << 'PY'
from fastapi import FastAPI
from pydantic import BaseModel
from maintenance_intelligence.runner.core import run
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.logging import setup_logger

app = FastAPI(title="Maintenance Intelligence API", version="0.1.0")
settings = Settings()
setup_logger(settings.log_level)

class TriggerPayload(BaseModel):
    event_id: str

@app.post("/api/v1/agents/rca/trigger")
def trigger_rca(p: TriggerPayload):
    return run(p.event_id, settings)
PY

# CI
cat > .github/workflows/ci.yml << 'PY'
name: ci
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.11" }
    - run: pip install --upgrade pip && pip install .[dev]
    - run: ruff check .
    - run: black --check .
PY

# README (short)
cat > README.md << 'PY'
# Maintenance Intelligence

This branch introduces:
- Kafka/PG services split (simulator, ingestion, rca_agent, wo_bridge)
- Orchestrator (single-shot) + CLI and FastAPI
- Config via env (kafka bootstrap, PG DSN parts)
- DB bootstrap is a no-op (migrations recommended later)

Run services (separate terminals/processes):
- python -m maintenance_intelligence.services.simulator
- python -m maintenance_intelligence.services.ingestion
- python -m maintenance_intelligence.services.rca_agent
- python -m maintenance_intelligence.services.wo_bridge

Trigger single run:
- mi-runner rca --event-id E123

Next:
- Replace RCA stub with GenAI gateway + RAG
- Add OpenClaw cron + run summaries
- Add DB migrations & health endpoints
PY

# Commit + push
git add .
git commit -m "refactor: split Kafka/PG services, add orchestrator/CLI/API; DB bootstrap -> no-op"
git push -u origin "$BRANCH"