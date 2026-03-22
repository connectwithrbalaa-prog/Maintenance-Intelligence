# Demo Dry-Run Checklist

## 1. Environment Readiness
- API reachable at expected base URL.
- Portal loads without missing assets.
- Demo run summaries exist in outputs path.
- Postgres contains matching workorder/proposal/feedback data for demo org.

## 2. Identity Setup
- Use one demo identity for full run.
- Set role and org headers consistently.
- Verify identity endpoint response before starting:
  - GET /api/v1/whoami

## 3. Endpoint Smoke Checks
- GET /api/v1/portal/runs
- GET /api/v1/portal/runs/latest?asset_id=<demo_asset>
- GET /api/v1/portal/runs/<demo_run_id>
- GET /api/v1/signals/summary?asset_id=<demo_asset>&limit=6
- GET /api/v1/reports/prioritized-assets?limit=5&window=30
- GET /api/v1/reports/rca-outcomes?window=30

Expected:
- 200 responses for in-tenant data.
- No cross-tenant data visible.

## 4. Cross-Tenant Safety Spot Check
- Repeat one portal read with a different org header.
- Repeat one signals read with a different org header.
- Repeat one reports/outcomes read with a different org header.

Expected:
- filtered-empty or denied response depending on endpoint path.

## 5. Script Rehearsal (10 min)
- Opening value statement: 1 min.
- Portal run list and detail: 4 min.
- PM follow-through and repair plan: 2 min.
- Prioritized assets + outcomes: 2 min.
- Trust and close: 1 min.

## 6. Fallback Paths
- Known-good run id ready.
- Known-good asset id ready.
- Backup path if sparse signals:
  - continue from run detail to outcomes and close.

## 7. Demo Operator Rules
- Do not change tenant identity mid-session.
- Do not open internal debug tooling in front of customer.
- Keep flow product-first, dashboards second.

## 8. Post-Demo Capture
- Record top 3 customer outcomes requested.
- Record blocker questions about connectors/governance.
- Record pilot scope recommendation and timeline.
