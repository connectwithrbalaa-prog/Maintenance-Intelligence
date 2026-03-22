# Customer Packet: Manufacturing (Ready to Present)

## Customer Session Header
- Customer account: <fill>
- Session date: <fill>
- Presenter: <fill>
- Customer roles attending: <fill>
- Demo identity org scope: <fill>

## Positioning
Maintenance Intelligence reduces line-impacting decision latency by converting anomaly signals into actionable, traceable maintenance execution.

## What to Emphasize
- CNC spindle and conveyor-drive style assets
- bearing wear and thermal drift style failure patterns
- impact on line uptime, schedule adherence, and OEE

## 12-Minute Manufacturing Script
1. Open with line-impact framing (1 min)
2. Show run detail decision quality (4 min)
3. Show PM follow-through and repair plan (3 min)
4. Show prioritized assets and outcomes trend (3 min)
5. Close with pilot scope and KPI baseline ask (1 min)

## Demo Anchors (Fill Before Session)
- Primary run id: <fill>
- Backup run id: <fill>
- Primary asset id: <fill>
- Backup asset id: <fill>

## Preflight Checklist (T-30 to T-5)
1. Confirm API and portal are reachable in the demo environment.
2. Confirm the selected identity and org scope via whoami.
3. Confirm primary and backup run ids return in-tenant run detail.
4. Confirm one signals view, one prioritized-assets view, and one outcomes view return valid responses.
5. Confirm no cross-tenant data appears for the chosen demo identity.

## Live Run Sequence (Presenter Quick Guide)
1. Open with production impact:
"We reduce time from anomaly detection to maintenance action for line-critical assets, with traceable follow-through."
2. Run detail proof:
Show hypothesis, confidence, immediate actions, and PM suggestions for the primary run.
3. Execution proof:
Show proposal status, approval history, and repair-plan details.
4. Portfolio proof:
Show prioritized assets and outcomes trend snapshot.
5. Security trust line:
"Customer-visible reads and actions are authenticated and tenant-scoped; cross-tenant access is filtered or denied."
6. Decision ask:
Use the pilot ask below and secure alignment on KPI baselines.

## Manufacturing KPI Set for Pilot
- triage cycle time
- recommendation acceptance rate
- completed follow-through volume
- repeat failure rate on pilot asset class

## Pilot Success Gate (Exit Criteria)
- Baseline and endline KPI measurements are captured for the same asset class and org/site scope.
- At least one accepted recommendation proceeds to visible follow-through.
- Customer stakeholders agree on scale-up or next validation wave.

## Pilot Ask
"Approve a 2-to-4-week pilot on one production line and one critical asset class, measuring triage latency, recommendation acceptance, and schedule-impact reduction."

## Risk Questions and Answers
- "Will this disrupt line operations?"
  - "No. It overlays decision and handoff flow around existing operations and CMMS process."
- "How does this affect quality and traceability?"
  - "Decision and handoff actions remain visible and auditable in one workflow."
- "Can this scale across lines?"
  - "Yes, via phased rollout by line and asset class with KPI checkpoints."

## Failure Recovery (If Live Data Is Thin)
1. Pivot to the backup run id immediately.
2. Skip deep signals drilldown and continue to outcomes summary.
3. Keep the value narrative focused on decision quality and execution traceability.
4. Offer to share environment logs and detailed diagnostics after the customer session.

## 24-Hour Follow-Up Template
Subject: Manufacturing Demo Follow-Up - Pilot Scope and KPI Alignment

Thank you for the session today. As discussed, the recommended next step is a focused 2-to-4-week pilot on one production line and one critical asset class.

Proposed pilot KPI set:
- triage cycle time
- recommendation acceptance rate
- completed follow-through volume
- repeat failure rate on pilot asset class

If approved, we will align on pilot asset scope, KPI baselines, and review cadence in the kickoff meeting.
