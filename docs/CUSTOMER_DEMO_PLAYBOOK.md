# Customer Demo Playbook

## Objective
Present Maintenance Intelligence as a product workflow (not a dashboard collection), with clear business value and safe tenant-scoped behavior.

## Companion Assets
- Master index: `docs/DEMO_MASTER_INDEX.md`
- Demo packet run sheet: `docs/DEMO_PACKET_RUN_SHEET.md`
- Speaker notes (one-page): `docs/DEMO_SPEAKER_NOTES_ONE_PAGE.md`
- Anchor autofill guide: `docs/DEMO_ANCHOR_AUTOFILL.md`
- Manufacturing customer packet: `docs/DEMO_CUSTOMER_PACKET_MANUFACTURING.md`
- Oil and gas customer packet: `docs/DEMO_CUSTOMER_PACKET_OIL_GAS.md`
- Utilities customer packet: `docs/DEMO_CUSTOMER_PACKET_UTILITIES.md`
- Pharma customer packet: `docs/DEMO_CUSTOMER_PACKET_PHARMA.md`
- Presenter script: `docs/DEMO_PRESENTER_SCRIPT.md`
- One-slide summary: `docs/DEMO_ONE_SLIDE_SUMMARY.md`
- Dry-run checklist: `docs/DEMO_DRY_RUN_CHECKLIST.md`
- Day-of quick sheet: `docs/DEMO_DAY_OF_QUICK_SHEET.md`
- 15-minute fast flow: `docs/DEMO_15_MIN_FAST_FLOW.md`
- Vertical customization kit: `docs/DEMO_VERTICAL_CUSTOMIZATION_KIT.md`
- Plant operations script: `docs/DEMO_SCRIPT_PLANT_OPERATIONS.md`
- Maintenance leadership script: `docs/DEMO_SCRIPT_MAINTENANCE_LEADERSHIP.md`
- CTO/platform script: `docs/DEMO_SCRIPT_CTO_PLATFORM.md`
- Openers and closers: `docs/DEMO_OPENERS_CLOSERS.md`
- Objection handling matrix: `docs/DEMO_OBJECTION_HANDLING_MATRIX.md`
- 30-minute executive flow: `docs/DEMO_EXECUTIVE_30_MIN_FLOW.md`

## Frontend Strategy
- Primary UI: Portal
- Secondary proof layer: Grafana dashboards
- Avoid adding a new frontend stack for this demo

Why:
- Portal shows operator/planner workflows end-to-end.
- Grafana supports credibility with observability and KPI evidence.
- A new frontend now adds integration and regression risk without improving demo confidence.

## Pre-Demo Checklist (T-30 to T-10)
1. Environment
- API is up and reachable.
- Portal page loads and static assets render.
- Demo data for one org is present in outputs and Postgres.

2. Identity and tenant context
- Use one explicit demo identity.
- Use org-scoped headers consistently for the whole session.
- Confirm whoami view shows expected role and org.

3. Data sanity
- At least one high-confidence RCA run exists.
- One PM proposal has visible follow-through metadata.
- Repair plan snapshot and parts are available for at least one run.
- Prioritized assets and outcomes return non-empty values for the demo org.

4. Safety checks
- Cross-tenant reads are not visible for portal/signals/reports/outcomes.
- Keep demo in one tenant narrative to avoid confusion.

## 10-Minute Demo Flow (Default)
1. Frame the problem (1 min)
- "We reduce time-to-action from anomaly to validated maintenance decision."

2. Portal run list to run detail (2 min)
- Open latest relevant run.
- Show title, confidence, hypothesis, immediate actions, PM suggestions.
- Show context and evidence references.

3. PM follow-through and repair plan (3 min)
- Show proposal state and handoff metadata.
- Show repair plan snapshot, key steps, and parts.
- Emphasize operator readability and actionability.

4. Triage and outcomes in product context (2 min)
- Show prioritized assets.
- Show outcomes summary (acceptance trend, handoff state trend, top entities).

5. Trust and controls (1 min)
- Mention tenant-scoped access and authenticated routes.
- Mention role-aware operations for approval flows.

6. Close (1 min)
- Summarize: faster triage, clearer decisions, measurable follow-through.

## 20-Minute Demo Flow (Expanded)
1. Full 10-minute flow.
2. Add a compare view between two runs for drift in confidence/actions/evidence.
3. Show early-warning behavior and explain how trend signals influence prioritization.
4. Show a rejected/failed handoff case and how retry/audit history is preserved.
5. Open Grafana for supporting proof:
- outcomes dashboard for leadership trends
- observability dashboard for reliability posture and lag/backlog confidence

## Presentation Script Cues
- "Portal first" language:
  - "This is the operator and planner experience."
- "Grafana second" language:
  - "This validates operational reliability and adoption outcomes behind the workflow."
- Avoid saying:
  - "This is still mostly a demo UI"
  - "This is just dashboards"

## Handling Customer Questions
1. "Is this production ready?"
- "This demo is tenant-scoped and auth-hardened on customer-visible surfaces. Full production auth hardening is already planned as the next rollout phase."

2. "Can we integrate with our CMMS?"
- "Yes. The workflow is connector-driven; this demo shows the handoff lifecycle and audit path."

3. "How do you prevent cross-tenant visibility?"
- "Customer-visible reads and actions are authenticated and tenant-scoped; cross-tenant access is filtered or denied."

## Fallback Plan (if live data has an issue)
1. Use a known-good run id and jump directly to run detail.
2. Skip live signal drilldown if source data is sparse.
3. Use outcomes summary and then pivot to Grafana proof.
4. Keep the narrative centered on workflow value, not raw query output.

## Operator Notes
- Keep one identity for the full session.
- Avoid changing org headers mid-demo.
- Do not open internal debug tooling during customer flow.
- If an endpoint returns partial data, narrate the stable fields and continue.

## Post-Demo Follow-Up Template
- Business value observed:
  - Reduced triage ambiguity
  - Faster path to maintenance action
  - Clearer approval and handoff traceability
- Suggested next step:
  - Pilot with one asset class and one site/org scope
  - Expand connectors and governance in production phase
