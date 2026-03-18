# Single PR Fallback Body

## Summary

This PR delivers the current `feature/rca-structured-output` tranche against `main`.

It expands the product from an RCA prototype into a broader operational workflow covering:

- structured RCA generation and persisted repair plans
- prioritized asset scoring and triage workflows
- PM approval, retry, and follow-through UX
- handoff queue diagnostics and operator controls
- edge-mode buffering, replay, and degraded local inference
- observability, deployment scaffolding, and supporting tests

## Scope

### RCA and Repair Planning

- added structured RCA output integration
- secured RCA reads
- persisted structured repair plans
- surfaced RCA evidence context in the portal
- added evidence drift and repair-plan drift views
- expanded context assembly with fleet-wide retrieval support

### PM Workflows and Outcomes

- hardened PM approval responses and idempotent retries
- added approval audit history and audit paging
- added admin retry controls and audit origin tracking
- expanded outcomes metrics and lifecycle timestamp persistence
- aligned schema and migration coverage

### Prioritized Scoring and Triage

- added prioritized asset risk scoring
- wired prioritized scoring into portal triage
- added triage drill-through and evidence deep-linking
- added deterministic PdM early-warning scoring
- highlighted and ordered PdM-critical and elevated assets
- added optional warnings-only triage filtering

### Portal Handoff Queue UX

- added PM follow-through snapshotting and richer proposal responses
- added handoff queue views, sort controls, and per-user preferences
- surfaced SLA aging signals, retries remaining, connector-failure views, and empty states
- added summary chips for lead age, aging risk, visible classes, longest wait, and active sort state

### Edge Resilience

- added opt-in local event buffering and replay for ingestion
- added command buffering and replay for CMMS handoff
- exposed edge diagnostics in metrics, health, and portal status surfaces
- added deterministic local RCA fallback when GenAI is unavailable in edge mode

### Platform and Delivery

- added observability and deployment scaffolding
- hardened runtime config and migration fallbacks
- updated developer docs and release artifacts

## Validation

Validation was run incrementally while building the branch, including focused coverage around:

- RCA structured, stub, and integration paths
- PM proposal APIs and retry behavior
- portal diagnostics and queue rendering
- edge event buffering and command replay
- metrics and deep health surfaces
- WO bridge replay behavior
- migration and outcomes smoke coverage

## Known Follow-up Gaps Relative to the BRD

This branch does not fully close the BRD. Remaining follow-up areas include:

- production auth and tenant isolation
- stronger audit and security hardening
- connector expansion beyond Maximo and mock
- governed or pre-cached context infrastructure
- notification routing and workflow delivery surfaces
- richer domain-pack and asset/site metadata coverage

## Review Guidance

Recommended review order:

1. RCA foundation and repair-plan persistence
2. PM workflow and outcomes changes
3. prioritized scoring and triage UX
4. handoff queue and portal operator workflow
5. edge buffering, replay, and fallback behavior
6. observability, config, and docs