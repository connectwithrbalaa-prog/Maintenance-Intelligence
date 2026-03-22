# Day-of-Demo Quick Sheet

## Purpose
Two-page operator sheet for live demo day: what to verify, what to say, and what to do if something fails.

## Page 1: Pre-Flight (T-30 to T-5)

### 1. Environment
- API is reachable.
- Portal loads successfully.
- Demo org data exists in outputs and backing DB.

### 2. Identity
- Use one identity and one org for full session.
- Verify identity quickly:
  - GET /api/v1/whoami

### 3. Must-pass endpoint checks
- GET /api/v1/portal/runs
- GET /api/v1/portal/runs/latest?asset_id=<asset>
- GET /api/v1/portal/runs/<run_id>
- GET /api/v1/signals/summary?asset_id=<asset>&limit=6
- GET /api/v1/reports/prioritized-assets?limit=5&window=30
- GET /api/v1/reports/rca-outcomes?window=30

Expected:
- 200 for in-tenant data.
- No cross-tenant data visible.

### 4. Known-good anchors
- Primary run id: <fill>
- Backup run id: <fill>
- Primary asset id: <fill>
- Backup asset id: <fill>

### 5. One-line opening
"We turn anomaly signals into actionable maintenance decisions with traceable follow-through."

## Page 2: Live Run and Recovery

### 1. Core sequence
1. Portal run list and detail
2. PM follow-through and repair-plan snapshot
3. Prioritized assets and outcomes
4. Optional Grafana proof

### 2. Time boxes
- Opening: 1 min
- Run detail: 4 min
- Follow-through: 3 min
- Outcomes: 2 min

### 3. Recovery if live data is thin
- Jump to known-good run detail.
- Skip signals drilldown.
- Continue to outcomes and close.

### 4. Recovery if endpoint fails
- State: "I’ll continue with the validated workflow view and follow up with environment logs after this session."
- Continue with next panel; do not debug live.

### 5. Hard guardrails
- Do not switch org headers mid-demo.
- Do not open debug tooling during customer flow.
- Keep narrative product-first, dashboard-second.

### 6. One-line close
"The value is faster triage, higher decision confidence, and measurable execution outcomes."
