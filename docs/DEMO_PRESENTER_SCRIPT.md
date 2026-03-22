# Demo Presenter Script

## Index
- Master index: `docs/DEMO_MASTER_INDEX.md`

## Audience-Specific Variants
- Plant operations: `docs/DEMO_SCRIPT_PLANT_OPERATIONS.md`
- Maintenance leadership: `docs/DEMO_SCRIPT_MAINTENANCE_LEADERSHIP.md`
- CTO or platform: `docs/DEMO_SCRIPT_CTO_PLATFORM.md`

## Advanced Presenter Aids
- Demo packet run sheet: `docs/DEMO_PACKET_RUN_SHEET.md`
- Openers and closers: `docs/DEMO_OPENERS_CLOSERS.md`
- Objection handling matrix: `docs/DEMO_OBJECTION_HANDLING_MATRIX.md`
- 30-minute executive flow: `docs/DEMO_EXECUTIVE_30_MIN_FLOW.md`
- Day-of quick sheet: `docs/DEMO_DAY_OF_QUICK_SHEET.md`
- 15-minute fast flow: `docs/DEMO_15_MIN_FAST_FLOW.md`
- Vertical customization kit: `docs/DEMO_VERTICAL_CUSTOMIZATION_KIT.md`

## Audience Modes
- Operations audience: emphasize triage speed, actionability, and handoff confidence.
- Leadership audience: emphasize cycle time, acceptance trends, and measurable outcomes.

## 10-Minute Script

### 0:00 to 1:00 - Opening
"Today I will show how Maintenance Intelligence turns asset anomalies into actionable maintenance decisions with traceable follow-through. We will stay in a single tenant context for this walkthrough."

### 1:00 to 3:00 - Portal Run Overview
- Open portal run list.
- Pick the latest high-signal run.

Talk track:
"This is the operator and planner workspace. Each run contains the RCA hypothesis, immediate actions, PM suggestions, and confidence so teams can decide quickly without jumping across systems."

### 3:00 to 5:00 - Run Detail and Evidence
- Open run detail.
- Highlight hypothesis, immediate actions, PM suggestions, confidence, context references.

Talk track:
"The detail view gives us decision context and evidence in one place. Instead of an alert with no guidance, this provides a reasoned recommendation and next actions."

### 5:00 to 7:00 - PM Follow-Through and Repair Plan
- Show proposal/approval state.
- Show handoff state and audit trail.
- Show persisted repair-plan snapshot and parts.

Talk track:
"This is where recommendation becomes execution. We preserve approval history, handoff state, and repair-plan details so follow-through is auditable and operationally usable."

### 7:00 to 8:30 - Prioritized Assets and Outcomes
- Show prioritized-assets panel.
- Show outcomes panel for acceptance and handoff trends.

Talk track:
"This gives supervisors a live queue and outcomes trend. We can prioritize what to fix first and measure if recommendations are being accepted and completed."

### 8:30 to 9:30 - Trust and Controls
Talk track:
"All demo-visible reads and actions are authenticated and tenant-scoped. Cross-tenant access is filtered or denied."

### 9:30 to 10:00 - Close
Talk track:
"The business impact is faster triage, better decision quality, and traceable maintenance execution."

## 20-Minute Expansion
1. Run the full 10-minute script.
2. Add run-to-run comparison to explain drift in confidence/actions/evidence.
3. Show an incomplete/failure handoff and retry behavior.
4. Open Grafana as supporting proof:
- outcomes dashboard for KPI trends
- observability dashboard for reliability posture

## Q&A Answers

### Is this production ready?
"This demo is auth-hardened for customer-visible surfaces and tenant-scoped end to end on the demo path. The full production hardening checklist is already planned and sequenced."

### How does this integrate with CMMS?
"Through connector-based handoff with audit history and status normalization, so maintenance actions are traceable from recommendation to work-order lifecycle."

### How do you prevent data leakage between tenants?
"Requests are authenticated and tenant scope is enforced on read and action surfaces. Cross-tenant data is not returned on these endpoints."

## Presenter Notes
- Keep one identity and one org for the entire live session.
- Do not switch headers mid-demo.
- If a panel is sparse, continue with the next value step instead of debugging live.
