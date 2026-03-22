# Customer Send Pack: Manufacturing

## Purpose
Single outbound packet for customer demo delivery, pilot alignment, and 24-hour follow-up.

## Session Header
- Customer account: <fill>
- Session date: <fill>
- Presenter: <fill>
- Customer roles attending: <fill>
- Demo identity org scope: <fill>

## Executive Value Statement
Maintenance Intelligence reduces line-impacting decision latency by converting anomaly signals into actionable, traceable maintenance execution.

## Live Agenda (12 Minutes)
1. Line-impact framing (1 min)
2. Run-detail decision quality (4 min)
3. PM follow-through and repair plan (3 min)
4. Prioritized assets and outcomes trend (3 min)
5. Pilot KPI ask (1 min)

## Demo Anchors (Required)
- Primary run id: <fill>
- Backup run id: <fill>
- Primary asset id: <fill>
- Backup asset id: <fill>

## Preflight Checklist
1. API and portal reachable in demo environment.
2. Identity and org scope verified via whoami.
3. Primary and backup runs return in-tenant detail.
4. Signals, prioritized-assets, and outcomes views return valid responses.
5. Cross-tenant data is not visible for selected identity.

## Core Talk Track
- Opening line:
"We reduce time from anomaly detection to maintenance action for line-critical assets, with traceable follow-through."
- Trust line:
"Customer-visible reads and actions are authenticated and tenant-scoped; cross-tenant access is filtered or denied."
- Decision close:
"Approve a focused pilot with agreed KPI baselines and a 2-to-4-week review checkpoint."

## Pilot KPI Set
- triage cycle time
- recommendation acceptance rate
- completed follow-through volume
- repeat failure rate on pilot asset class

## Pilot Success Gate
- Baseline and endline KPI measurements captured for same asset class and org/site scope.
- At least one accepted recommendation proceeds to visible follow-through.
- Stakeholders agree on scale-up or next validation wave.

## Objection Handling (Quick)
- "Will this disrupt line operations?"
  - "No. It overlays decision and handoff flow around existing operations and CMMS process."
- "How does this affect quality and traceability?"
  - "Decision and handoff actions remain visible and auditable in one workflow."
- "Can this scale across lines?"
  - "Yes, via phased rollout by line and asset class with KPI checkpoints."

## Failure Recovery
1. Pivot to backup run id.
2. Skip deep signals drilldown.
3. Continue to outcomes summary and pilot ask.
4. Share diagnostics after session, not during session.

## 24-Hour Follow-Up Email
Subject: Manufacturing Demo Follow-Up - Pilot Scope and KPI Alignment

Thank you for the session today. As discussed, the recommended next step is a focused 2-to-4-week pilot on one production line and one critical asset class.

Proposed pilot KPI set:
- triage cycle time
- recommendation acceptance rate
- completed follow-through volume
- repeat failure rate on pilot asset class

If approved, we will align on pilot asset scope, KPI baselines, and review cadence in the kickoff meeting.
