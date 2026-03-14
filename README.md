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

## GenAI Gateway (OpenAI) & Run Summaries

- Set OPENAI_API_KEY to enable GenAI RCA drafts.
- Defaults:
  - MI_GENAI_MODEL=gpt-4.1
  - MI_GENAI_TIMEOUT_S=25
  - MI_RUN_SUMMARY_DIR=outputs (JSON artifacts per run)
- RCA agent includes model_version/tokens/latency in recommendation.model.

## Database Migrations & Health Checks

- Run migrations:
  - python -m maintenance_intelligence.db.migrate
- Health endpoint:
  - GET /healthz (basic)
  - GET /healthz?deep=true (PG + Kafka checks)

## OpenClaw Cron Wiring (Scheduled RCA Test)

This repo provides a cron-friendly CLI and wrapper:
- Trigger a synthetic RCA test: `mi-runner rca-test`
- Cron wrapper: `scripts/cron_rca_test.sh` (writes to `logs/cron_rca_test.log` and prints JSON)

Environment:
- `OPENAI_API_KEY` (for GenAI output; otherwise stub text is used)
- Optional:
  - `MI_RUN_SUMMARY_DIR` (default: `outputs`)
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

GenAI:
- OPENAI_API_KEY (required for live GenAI RCA)
- MI_GENAI_MODEL (default: gpt-4.1)
- MI_GENAI_TIMEOUT_S (default: 25)

Outputs / Logs:
- MI_RUN_SUMMARY_DIR (default: outputs)
- MI_CRON_LOG_DIR (default: logs)

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

Utilities:
- mi-runner rca --event-id E123
- mi-runner rca-test
- mi-runner export-bad-actors --limit 50
- scripts/cron_rca_test.sh (cron-friendly)

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

## Structured RCA Output

- Gateway returns strict JSON with:
  - title, hypothesis[], evidence_ids[], immediate_actions[], pm_suggestions[], confidence (0..1)
- rca_agent uses structured fields to set recommendation title/rationale/evidence and carries confidence in model metadata.
- Run summaries include the structured payload for traceability.

### Outcomes Per-Asset & Resolution Timestamp

- TTR now prefers `workorders.metadata.resolved_at` and falls back to `created_at` when missing.
- TTR linkage prefers `metadata.evidence_event_id`; otherwise it uses the nearest same-asset event within `MI_TTR_FALLBACK_WINDOW_H` hours.
- API / CSV include:
  - per_asset_acceptance: rate, accepts, total
  - per_asset_ttr: average TTR seconds by asset

## Multi-Tenant and RBAC

- `MI_MULTI_TENANT=true` enables org-aware query scoping for outcomes, feedback, bad-actors, context assembly, and RAG document retrieval.
- `MI_AUTH_MODE=none|api_key` controls request auth. In `api_key` mode, send `X-API-Key` and configure `MI_API_KEYS` as JSON: `{"key-1":{"org_id":"org-a","role":"viewer"}}`.
- Roles:
  - `viewer`: read scoped reports and signals
  - `operator`: viewer permissions plus RCA trigger and feedback submission
  - `admin`: full access in the current stub
- Kafka topic strategy:
  - `MI_KAFKA_TENANT_MODE=message`: keep shared topics and filter by `org_id` in the consumer
  - `MI_KAFKA_TENANT_MODE=namespaced`: publish and consume `canonical.{org_id}.*` topics for single-org worker deployments
- Single-tenant deployment:
  - leave `MI_MULTI_TENANT=false` and `MI_AUTH_MODE=none`
- Multi-tenant deployment:
  - enable `MI_MULTI_TENANT=true`
  - provision per-org API keys via `MI_API_KEYS`
  - run workers with the org selected by `MI_DEFAULT_ORG` when using namespaced Kafka topics
