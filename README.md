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

## Signals Tenant Isolation

- `signals` and `signal_rollups` now carry `org_id` for end-to-end tenant isolation in the context path.
- Signal ingestion writes `org_id` from the incoming event, falls back to `lineage.org_id`, and then to `MI_DEFAULT_ORG`.
- The SQL migration backfills existing `signals.org_id` from stored metadata where available; historical rollups without source org metadata may remain null until recomputed.

## Prompt Catalog and A/B Testing

- Prompt templates are versioned in `prompt_catalog` with IDs, route ownership, descriptions, and intended-use metadata.
- Route-level defaults and org-specific overrides are stored in `prompt_route_configs`.
- `MI_PROMPT_DEFAULTS` and `MI_PROMPT_CANARY_DEFAULTS` provide config-backed fallbacks when no DB override exists.
- `MI_PROMPT_CANARY_RATIO` controls the default canary split; the RCA agent records `prompt_id` and variant in run summaries and recommendation model metadata.
- Feedback can carry `prompt_id` and `prompt_route`, enabling prompt quality tracking via `prompt_feedback_total` and auto-rollback decisions.

## PM Advisor Skeleton

- New PM advisory endpoints live under `/api/v1/agents`:
  - `POST /pm/advisor/analyze` creates a draft PM change proposal from an RCA recommendation.
  - `POST /playbooks/search` returns stub playbook matches for planner review.
  - `GET /pm/proposals` lists scoped proposal drafts.
  - `POST /pm/proposals/{proposal_id}/approve` marks a proposal approved and sends it through the configured CMMS connector.
  - PM proposal endpoints resolve identity from `request.state.user` first, then guarded dev headers, and finally the configured auth mode fallback.
  - Proposal responses include `org_id` and `proposer_subject` so the portal can reflect backend identity consistently.
- Thin portal preview:
  - `GET /portal/pm-approvals` serves a single-page planner review UI backed by the PM proposal endpoints.
  - `GET /api/v1/whoami` returns `{org_id, role, subject}` from request context when available.
  - Dev header fallback via `X-Org-Id`, `X-Role`, and `X-Subject` is honored only when `MI_DEV_ALLOW_HEADERS=true`.
  - The portal sends explicit dev headers from its local controls, but it fails clearly when backend identity is unavailable and the env guard is off.
- Manual check:
  - Create a PM proposal through the advisor API.
  - Open `/portal/pm-approvals` and verify the draft renders.
  - Verify `/api/v1/whoami` returns the expected role from auth context or dev headers.
  - Switch fallback role state to `viewer` only when backend identity is unavailable and confirm approve actions are disabled.
  - Use an `operator` or `admin` identity, approve a proposal, and confirm the CMS handoff reference is shown.
  - Use `scripts/demo_pm_approval.sh` for a curl-based end-to-end staging demo against the shipped PM advisor routes.
- Schema:
  - Alembic revision `005_pm_change_proposals`
  - Alembic revision `006_pm_change_proposals_identity`
  - SQL fallback migration `008_pm_change_proposals.sql`
  - SQL fallback migration `009_pm_change_proposals_identity.sql`
- `MI_PM_CONNECTOR_BACKEND` defaults to `mock`, which returns a realistic draft work-order payload and keeps the approval path behind a swappable adapter boundary.
- The CMMS connector entry point lives behind `maintenance_intelligence/services/cmms.py`; add a real connector there before rollout.

## Environment & Dev Mode

- `MI_DEV_ALLOW_HEADERS` defaults to `false` and should only be enabled for local development or isolated test environments.
- `MI_PM_CONNECTOR_BACKEND` defaults to `mock`; switch it only after adding a real connector implementation behind the same adapter interface.
- When enabled, `/api/v1/whoami` and the PM proposal endpoints may honor `X-Org-Id`, `X-Role`, and `X-Subject` for developer-controlled identity.
- When disabled, real request-context auth is required; header-only identity returns null from `/api/v1/whoami` and PM proposal actions reject unauthenticated access.

Local examples:

- Run the API locally with guarded dev headers enabled:
  - `MI_DEV_ALLOW_HEADERS=true uvicorn maintenance_intelligence.api.main:app --reload`
- Run the focused auth and PM advisor tests with guarded dev headers enabled:
  - `MI_DEV_ALLOW_HEADERS=true pytest tests/test_pm_advisor_identity.py tests/test_whoami.py tests/test_whoami_header_guard.py`
- If you use the existing compose stack for local review, set the API service env override to `MI_DEV_ALLOW_HEADERS=true` only in your local override file.
- Run the demo helper with an existing bearer token:
  - `BASE_URL=https://staging.example.com AUTH_BEARER_TOKEN="$TOKEN" ./scripts/demo_pm_approval.sh`
- The demo helper also accepts `API_URL` as an alias for `BASE_URL` and `--api-url` on the command line.
- `--use-existing-api` and `DEMO_PM_START_API=false` are accepted for compatibility; this branch's demo script always targets a running API instead of starting uvicorn.
- JSON output is pretty-printed with `jq` when available and otherwise falls back to `python -m json.tool`.
- Token-fetch examples for Keycloak-style and Okta-style flows are included in `scripts/demo_pm_approval.sh`; substitute your own token endpoint, client, and user credentials.

Staging / production checklist:

- Ensure upstream auth middleware populates `request.state.user` before exposing the portal or PM approval endpoints.
- Leave `MI_DEV_ALLOW_HEADERS` unset or explicitly set it to `false`.
- Verify `GET /api/v1/whoami` returns real request-context identity without developer headers.
- Verify the PM approval flow still works end to end through `/portal/pm-approvals` and the PM proposal API.
- Confirm header-only requests do not gain identity in staging or production.

## Cost and Latency Dashboards v2

- RCA runs now export `rca_cost_usd_total{model,prompt_id}` using a token-based estimate derived from `MI_RCA_MODEL_RATES`.
- Model latency is exported via `rca_latency_seconds{service,model,prompt_id}` while the existing `rca_duration_seconds{service}` still tracks full agent runtime.
- Budget caps are exposed via `rca_budget_cap_usd{window}` using `MI_RCA_BUDGET_CAPS_USD` for daily and weekly utilization panels.
- Prompt acceptance rate is derived from `prompt_feedback_total{route,prompt_id,action}` in PromQL rather than stored as a separate gauge.
- RCA run summaries now persist `estimated_cost_usd` alongside tokens and latency for per-run auditability.
- Dashboard and alert assets live under `monitoring/grafana/rca_observability_v2.dashboard.json` and `monitoring/prometheus/rca_observability_v2_alerts.yml`.

## Rollout and Operations Docs

- Rollout guide: `docs/v0.3.0-rollout-guide.md`
- Operator checklist: `docs/v0.3.0-operator-checklist.md`
