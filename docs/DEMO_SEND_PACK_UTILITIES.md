# Customer Send Pack: Utilities and Energy

## Purpose
Single outbound packet for customer demo delivery, pilot alignment, and 24-hour follow-up.

## Session Header
- Customer account: <fill>
- Session date: <fill>
- Presenter: <fill>
- Customer roles attending: <fill>
- Demo identity org scope: <fill>

## Executive Value Statement
Maintenance Intelligence helps utility teams prioritize reliability risks faster and execute corrective actions with traceable operational controls.

## Live Agenda (12 Minutes)
1. Reliability and SLA framing (1 min)
2. Run-detail decision clarity (4 min)
3. PM follow-through and repair-plan snapshot (3 min)
4. Prioritized assets and outcomes trends (3 min)
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
"We reduce time from anomaly detection to maintenance action for reliability-critical utility assets, with traceable follow-through."
- Trust line:
"Customer-visible reads and actions are authenticated and tenant-scoped; cross-tenant access is filtered or denied."
- Decision close:
"Approve a focused pilot with agreed KPI baselines and a 2-to-4-week review checkpoint."

## Pilot KPI Set
- triage cycle time
- recommendation acceptance rate
- corrective action completion rate
- repeat incident rate on pilot assets
- MTTR trend on pilot assets

## Pilot Success Gate
- Baseline and endline KPI measurements captured for same asset class and org/site scope.
- At least one accepted recommendation proceeds to visible follow-through.
- Stakeholders agree on scale-up or next validation wave.

## Objection Handling (Quick)
- "How does this support reliability operations?"
  - "It provides faster prioritization and clearer follow-through visibility for reliability-critical assets."
- "How do we ensure controlled access?"
  - "Customer-visible reads and actions are authenticated and tenant-scoped; cross-tenant access is filtered or denied."
- "Can this coexist with current operations tooling?"
  - "Yes. It augments decision and handoff flow, not a forced rip-and-replace."

## Failure Recovery
1. Pivot to backup run id.
2. Skip deep signals drilldown.
3. Continue to outcomes summary and pilot ask.
4. Share diagnostics after session, not during session.

## 24-Hour Follow-Up Email
Subject: Utilities Demo Follow-Up - Pilot Scope and KPI Alignment

Thank you for the session today. As discussed, the recommended next step is a focused 2-to-4-week pilot on one org/site and one critical utility asset class.

Proposed pilot KPI set:
- triage cycle time
- recommendation acceptance rate
- corrective action completion rate
- repeat incident rate on pilot assets
- MTTR trend on pilot assets

If approved, we will align on pilot asset scope, KPI baselines, and review cadence in the kickoff meeting.
