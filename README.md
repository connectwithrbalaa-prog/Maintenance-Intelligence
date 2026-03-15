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

## RCA Workflow

The current RCA path in this branch is centered on the Kafka-driven `rca_agent` flow, with a thin single-run trigger for smoke and demo use.

### Implemented Now

1. Event ingestion publishes canonical events to `canonical.event.raised`.
2. `maintenance_intelligence.services.rca_agent` consumes `alarm` and `anomaly` events from that topic.
3. `maintenance_intelligence.context.assembler.get_event_context(...)` assembles evidence for the event:
  - recent work order titles for the asset
  - recent signals and rollups when available
  - hybrid RAG document chunks when available, with graceful fallback
4. The RCA agent calls the GenAI gateway when `OPENAI_API_KEY` is configured, or falls back to a stub RCA draft when it is not.
5. The RCA output is normalized into structured fields such as `title`, `hypothesis`, `immediate_actions`, `pm_suggestions`, and `confidence`.
6. The RCA agent emits a canonical recommendation event to `canonical.recommendation.created`.
7. The RCA agent writes a run summary artifact to `outputs/YYYY-MM-DD/<run_id>.json`.
8. The portal API and static portal UI expose those run summaries for inspection.

What is currently tested in this branch:
- structured gateway output and RCA stub behavior
- context assembly and hybrid RAG import/smoke coverage
- signals and metrics endpoints
- portal list and detail views backed by run summary artifacts

### Planned / Next

The following are not part of the implemented RCA production flow in this branch yet:

- PM advisor and playbook agents as first-class production services
- identity-aware API behavior such as `whoami` and production auth wiring
- CMMS adapter factory and real production connector implementations
- staging or production credential paths for CMMS approval workflows
- vendor observability connectors such as Datadog, ServiceNow, ScienceLogic, or SafetyCulture
- automated end-to-end staging validation with real tokens and external systems
- model governance features such as prompt audit logs, usage tracking, and feedback-driven tuning

This separation is intentional: the branch currently defines and tests the RCA generation pipeline, while downstream PM workflow, identity, connector hardening, and vendor integration remain follow-on work.

## GenAI Gateway (OpenAI) & Run Summaries

- Set OPENAI_API_KEY to enable GenAI RCA drafts.
- Defaults:
  - MI_GENAI_MODEL=gpt-4.1
  - MI_GENAI_TIMEOUT_S=25
  - MI_RUN_SUMMARY_DIR=outputs (JSON artifacts per run)
- RCA agent includes model_version/tokens/latency in recommendation.model.

## RAG Hybrid Retrieval

- **Index**: IVFFlat index on `doc_chunks.embedding` for efficient ANN search (tuned for small datasets)
- **Retrieval**: Hybrid ranking combining BM25 (text matching) and vector cosine similarity with configurable weights
- **Context Budgeting**: Packs top chunks up to a token budget (rough estimate: 4 chars/token) without breaking JSON assembly
- **Ingestion**: Supports .txt, .md, .html files; HTML converted to clean text; optional bulk chunking per document
- **CLI**: `mi-runner rag --path ./docs --asset-id PUMP-101 --bulk-mode --chunk-size 1000`

Context assembler now uses hybrid retrieval with event-based queries for better RCA evidence.

## Database Migrations & Health Checks

- Run migrations:
  - python -m maintenance_intelligence.db.migrate
- Dev compose runs the one-shot `migrator` service before starting the API.
- Health endpoint:
  - GET /healthz (basic)
  - GET /healthz?deep=true (PG + Kafka checks)

### Kafka Lag in Health Checks

- Deep health (`/healthz?deep=true`) now includes consumer group lag.
- Env:
  - `MI_HEALTH_GROUPS` (default: agent-ingestion,agent-rca,agent-wo-bridge,agent-signals)
  - `MI_HEALTH_TOPICS` (default: canonical.asset.upserted,canonical.event.raised,canonical.recommendation.created)
  - `MI_HEALTH_MAX_LAG` (default: 1000)
  - `MI_HEALTH_TIMEOUT_S` (default: 5)
- Status is marked `degraded` if lag > `MI_HEALTH_MAX_LAG` or offsets cannot be determined.

## Observability

- Metrics:
  - Prometheus endpoint: GET /metrics
  - Key metrics: rca_runs_total, rca_failures_total, rca_duration_seconds, events_ingested_total, recommendations_created_total, wo_drafts_total, kafka_consume_lag{group=...}
- Tracing (optional):
  - Enable with OTEL_ENABLED=true
  - Configure OTLP exporter via standard OTEL_* env vars (e.g., OTEL_EXPORTER_OTLP_ENDPOINT)
- Dashboards:
  - dashboards/observability-starter.json — import into Grafana and wire to your Prometheus datasource

## OpenClaw Cron Wiring (Scheduled RCA Test)

This repo provides a cron-friendly CLI and wrapper:
- Trigger a synthetic RCA test: `mi-runner rca-test`
- Cron wrapper: `scripts/cron_rca_test.sh` (writes to `logs/cron_rca_test.log` and prints JSON)

Environment:
- `OPENAI_API_KEY` (for GenAI output; otherwise stub text is used)
- Optional:
  - `MI_RUN_SUMMARY_DIR` (default: `outputs`)

## Local Dev Stack (Compose) + Alerts

- Start stack: `docker compose -f docker-compose.dev.yml up -d`
  - Services: Kafka/ZooKeeper, Postgres, migrator, API, Prometheus, Alertmanager, Grafana
- The `migrator` service waits for Postgres, applies Alembic migrations, then the API starts.
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Import `dashboards/observability-starter.json` in Grafana
- Alerts:
  - Rules in `deploy/prometheus/alerts.yml`
  - Alertmanager at http://localhost:9093 (configure real receivers in `deploy/alertmanager/alertmanager.yml`)

Note:
- The API and migrator services use the repo code mounted at /app and install the app in-container at startup.
- For real RCA runs and RAG, set `OPENAI_API_KEY` in the api service environment or via a compose override.
  - `MI_CRON_LOG_DIR` (default: `logs`)

Example OpenClaw cron job (JSON):
{
  "action": "add",
  "job": {
    "name": "maintenance-intel-rca-test-hourly",
    "schedule": { "kind": "cron", "expr": "0 * * * *", "tz": "Asia/Kolkata" },
    "payload": {
      "kind": "agentTurn",
      "message": "Reminder: Run scheduled RCA test now (scripts/cron_rca_test.sh). Expect a new run_summary.json in outputs/.",
      "timeoutSeconds": 60
    },
    "sessionTarget": "isolated",
    "enabled": true
  }
}

If your OpenClaw runner can execute shell commands directly, schedule:
`/workspaces/Maintenance-Intelligence/scripts/cron_rca_test.sh`
and tail `logs/cron_rca_test.log`.

The wrapper outputs a single JSON line from `mi-runner rca-test`, which includes the event_id and run_id. The full run summary is stored at `outputs/YYYY-MM-DD/<run_id>.json`.

## Bad Actor Dashboard (Seed)

- API: GET /api/v1/reports/bad-actors?limit=20
  - Score = events_90d + 2*workorders_90d
  - Includes latest_severity and last_event_at (when available)
- CLI export:
  - mi-runner export-bad-actors --limit 50
  - Writes to outputs/reports/bad_actors_<YYYY-MM-DD>.json

## Configuration (Environment Matrix)

Core:
- MI_ENV (default: dev)
- MI_LOG_LEVEL (default: INFO)

Kafka / Postgres:
- KAFKA_BOOTSTRAP_SERVERS (default: kafka:9092)
- POSTGRES_DB (default: maintenance)
- POSTGRES_USER (default: postgres)
- POSTGRES_PASSWORD (default: postgres)
- POSTGRES_HOST (default: timescaledb)
- POSTGRES_PORT (default: 5432)

GenAI:
- OPENAI_API_KEY (required for live GenAI RCA)
- MI_GENAI_MODEL (default: gpt-4.1)
- MI_GENAI_TIMEOUT_S (default: 25)

Outputs / Logs:
- MI_RUN_SUMMARY_DIR (default: outputs)
- MI_CRON_LOG_DIR (default: logs)

## Outcomes Analytics

- API:
  - JSON: GET /api/v1/reports/rca-outcomes?window=30
  - CSV: GET /api/v1/reports/rca-outcomes/csv?window=30
- Metrics alignment:
  - rca_feedback_total{action=...} supports acceptance KPI panels.
- Dashboard:
  - dashboards/outcomes-starter.json (import into Grafana)

Copy .env.example to .env and set values as needed.

## Dev Quickstart

- make dev-install
- make migrate
- make api
- In separate terminals:
  - make run-sim
  - make run-ingest
  - make run-rca
  - make run-wo

Testing:
- make test
- make test-migrations

Utilities:
- mi-runner rca --event-id E123
- mi-runner rca-test
- mi-runner export-bad-actors --limit 50
- scripts/cron_rca_test.sh (cron-friendly)
- make demo-pm-approval

CLI note:
- `mi-runner` is available after `python -m pip install -e .` when the active virtualenv's `bin` directory is on `PATH`.
- If the script name is not on `PATH`, use `python -m maintenance_intelligence.runner.cli ...` instead.

PM demo flow:
- Starts the API with local header-based identity enabled
- Seeds a demo RCA run summary and analyzes it by `run_id` unless `--run-id` is provided
- Creates a PM proposal via `/api/v1/agents/pm/advisor/analyze`
- Approves that proposal via `/api/v1/agents/pm/proposals/{id}/approve`
- Uses the default `mock` CMMS adapter unless `MI_PM_CONNECTOR_BACKEND=maximo` is configured
- Use `DEMO_PM_START_API=false` or `scripts/demo_pm_approval.sh --use-existing-api` to target an already-running API
- Use `API_URL=http://host:port` or `scripts/demo_pm_approval.sh --api-url http://host:port` to point the demo at another endpoint
- Use `DEMO_PM_RUN_ID=<run-id>` or `scripts/demo_pm_approval.sh --run-id <run-id>` to target an existing run summary instead of generating a demo one
- If you point the script at an already-running API without `--run-id`, that API must be reading the same `MI_RUN_SUMMARY_DIR`
- The script pretty-prints JSON with `jq` when available and falls back to `python -m json.tool`

## Optional: pgvector RAG

- Enable extension + embedding column:
  - python -m maintenance_intelligence.db.migrate  (applies 002_pgvector.sql)
- Ingest docs:
  - mi-runner rag --path ./docs --asset-id PUMP-101
- Retrieval:
  - Context assembler tries vector similarity (pgvector) when available; falls back gracefully.

Notes:
- Requires OPENAI_API_KEY
- Embedding model can be set via MI_EMBED_MODEL (default: text-embedding-3-large)

## Signals Processing

- **signals** service: Consumes events, extracts measurements (vibration, temperature), computes rollups (1h/6h/24h mean/min/max), detects anomalies (threshold + z-score)
- **Context Assembler**: Includes recent signals and rollups in RCA context
- **API**: `/api/v1/signals/summary?asset_id=...` returns recent signals and rollups
- **CLI**: `mi-runner signals` runs the signals processor

Signals improve RCA evidence quality by providing measurement trends and anomaly flags.

## CMMS Connector Backend

- `MI_PM_CONNECTOR_BACKEND` selects the work-order connector backend.
  - `mock`: default adapter for local development and tests
  - `maximo`: staging-ready IBM Maximo scaffold with request/response mapping
- Maximo scaffold configuration:
  - `MI_MAXIMO_BASE_URL`
  - `MI_MAXIMO_SITE` (default: `BEDFORD`)
  - `MI_MAXIMO_API_KEY`
  - `MI_MAXIMO_TIMEOUT_S` (default: `15`)
- The current `wo_bridge` now delegates work-order creation through the adapter factory, but only the mock backend is intended for local execution. The Maximo adapter is a scaffold for staging integration and still requires real endpoint validation.
- Smoke harness:
  - `pytest -k maximo_smoke`
  - Uses `pytest-httpserver` to stand up a local Maximo-like endpoint and exercises the real HTTP adapter path without external credentials.
