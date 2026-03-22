# Demo Packet Run Sheet

## Session Purpose
Deliver a concise, high-confidence customer demo that shows workflow value, security posture, and a clear pilot next step.

## 1) Opening (30 to 45 seconds)
"We turn anomaly signals into actionable maintenance decisions with traceable follow-through, so teams move from alert noise to execution clarity faster."

## 2) 15-Minute Core Flow

### Minute 0 to 1: Value Frame
- Problem: anomaly-to-action latency and fragmented decision flow.
- Value: faster triage, clearer decisions, measurable follow-through.

### Minute 1 to 7: Portal Run Workflow
- Open run list and jump to known-good run.
- Show run detail:
  - hypothesis
  - confidence
  - immediate actions
  - PM suggestions
  - context/evidence references

Talk line:
"This is the decision layer: what likely happened, how sure we are, and what to do now."

### Minute 7 to 11: Execution Layer
- Show PM proposal status and approval history.
- Show handoff state.
- Show repair-plan snapshot and parts.

Talk line:
"This is execution traceability from recommendation through handoff and maintenance-ready plan details."

### Minute 11 to 14: Portfolio and Outcomes
- Show prioritized assets.
- Show outcomes trend snapshot.

Talk line:
"This helps teams decide what to work first and whether recommendations are being accepted and executed."

### Minute 14 to 15: Close and Ask
"Recommended next step is a focused pilot: one org/site and one critical asset class for 2-to-4 weeks with KPI baselines."

## 3) Objection Quick Responses

### "How is this different from dashboards?"
"Dashboards show what happened; this workflow guides what to do next and tracks execution."

### "Can we trust recommendations?"
"Decisions are shown with confidence, evidence context, and role-aware approval controls."

### "Will this replace CMMS?"
"No. It strengthens decision and handoff quality into your existing CMMS process."

### "How do you prevent tenant leakage?"
"Customer-visible reads and actions are authenticated and tenant-scoped; cross-tenant access is filtered or denied."

### "Is this production ready?"
"Demo-visible paths are hardened now; full production hardening is sequenced as the next rollout phase."

## 4) Day-of Anchors
- Primary run id: <fill>
- Backup run id: <fill>
- Primary asset id: <fill>
- Backup asset id: <fill>

## 5) Failure Recovery (Do Not Debug Live)
1. Jump to known-good run detail.
2. Skip sparse signal drilldown.
3. Continue with follow-through and outcomes.
4. Close with pilot ask and follow-up deep dive commitment.

## 6) Hard Guardrails
- Keep one identity and one org for the full session.
- Do not switch tenant headers during demo.
- Keep story portal-first, dashboards-second.
- Avoid opening internal debug tooling in front of customer.

## 7) Final Close (20 seconds)
"The value is faster triage, higher decision confidence, and measurable execution outcomes, delivered through a controlled and secure workflow."

## Companion References
- Playbook: `docs/CUSTOMER_DEMO_PLAYBOOK.md`
- Presenter script: `docs/DEMO_PRESENTER_SCRIPT.md`
- Speaker notes: `docs/DEMO_SPEAKER_NOTES_ONE_PAGE.md`
- Anchor autofill: `docs/DEMO_ANCHOR_AUTOFILL.md`
- 15-minute flow: `docs/DEMO_15_MIN_FAST_FLOW.md`
- Objection matrix: `docs/DEMO_OBJECTION_HANDLING_MATRIX.md`
- Day-of sheet: `docs/DEMO_DAY_OF_QUICK_SHEET.md`
