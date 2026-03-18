# BRD Follow-up Issue Drafts

This file captures the next issue set to open after the current structured RCA stack lands.

The goal is to cover the remaining BRD gaps that are not already addressed by the current open issues.

## Already Tracked Elsewhere

Do not re-open these as duplicates:

- `#27` Security: Audit logs for RCA triggers and feedback
- `#28` Security: IP allowlists and ingress enforcement notes
- `#13` RAG: pgvector index + hybrid retrieval

## Draft 1

### Title

Security: production auth, tenant isolation, and scoped RBAC enforcement

### Why now

The current stack still relies on lightweight identity resolution and does not fully meet the BRD bar for multi-tenant isolation, production auth integration, and tenant-scoped authorization.

### Scope

- Integrate a production-grade auth source for API identity
- Enforce org and site scoping across protected API routes
- Add tenant-aware role checks for RCA triggers, PM actions, and admin-only flows
- Define the trust model for forwarded identity headers and non-dev environments
- Ensure identity and authorization behavior composes cleanly with `#27` audit logging

### Acceptance Criteria

- Protected routes reject unauthenticated requests outside explicit demo or dev modes
- Org and site scope are enforced consistently on read and write paths
- Role checks for PM approval, retry, and RCA actions are explicit and tested
- Identity handling docs distinguish local demo behavior from production behavior
- Tests cover at least one authorized path and one cross-tenant rejection path

### Dependencies and Notes

- Related to `#27` and `#28`, but not duplicative
- This should likely land before any external notification or broad connector rollout

## Draft 2

### Title

Platform: governed context cache and prefetch pipeline for RCA and triage

### Why now

Context assembly is still primarily live and request-driven. The BRD calls for a more governed, pre-cached context layer so RCA and triage can stay responsive and consistent under higher load and degraded conditions.

### Scope

- Add a cache layer for assembled RCA and triage context
- Define cache keys by org, site, asset, and context scope
- Add prefetch or warm-up jobs for frequently accessed asset context
- Define invalidation rules tied to signals, workorders, and context source updates
- Expose freshness and cache-hit observability for operators

### Acceptance Criteria

- Frequently accessed assets can resolve context from cache rather than fully rebuilding on each request
- Cache entries are tenant-scoped and asset-scoped
- Freshness metadata is visible for cached context consumers
- Invalidation or refresh behavior is documented and tested
- Metrics expose cache hits, misses, and stale-entry refreshes

### Dependencies and Notes

- Builds on `#13`, but focuses on orchestration and governance rather than retrieval quality
- Could use Redis or another explicit cache backend, but the issue should stay outcome-focused

## Draft 3

### Title

Integrations: connector framework expansion beyond Maximo and mock backends

### Why now

The current CMMS handoff layer is still effectively limited to `mock` and `maximo`. The BRD expects a broader connector story and a cleaner path for adding new systems without rewriting core PM workflow logic.

### Scope

- Define a clearer connector contract for CMMS and adjacent operational systems
- Separate shared connector concerns such as retries, payload validation, and status normalization
- Add at least one additional real connector target or provide a scaffold that proves the contract
- Document connector configuration expectations and failure modes
- Ensure connector behavior composes with the existing edge buffering and replay logic

### Acceptance Criteria

- Connector contracts are documented and testable independent of one concrete backend
- Shared retry and error semantics are reusable across connectors
- At least one non-Maximo integration path is demonstrably supported or scaffolded
- Portal and PM workflow surfaces remain backend-agnostic
- Tests cover connector failure, retry, and status normalization paths

### Dependencies and Notes

- Should coordinate with `#36` stack edge behavior so replay semantics stay consistent across connectors

## Draft 4

### Title

Workflow: notification routing for RCA, approvals, and degraded operating states

### Why now

The current stack improves portal visibility and edge diagnostics, but the BRD still calls for workflow delivery beyond in-app status checks. Reviewers and operators need routed notifications when important actions or degraded modes require attention.

### Scope

- Define notification triggers for RCA completion, PM approval exceptions, connector failures, and degraded edge states
- Support at least one outbound delivery path such as email, webhook, or team chat integration
- Allow org-level routing configuration and severity mapping
- Add delivery status visibility for operators
- Document notification suppression and deduplication behavior

### Acceptance Criteria

- At least one notification channel is supported end to end
- RCA, PM, and edge-degradation events can emit routed notifications
- Notification routing is tenant-aware and configurable
- Delivery failures are visible and do not silently drop critical events
- Tests cover trigger, routing, and failure handling for one supported channel

### Dependencies and Notes

- Best scheduled after Draft 1 so routing can rely on stronger identity and tenant modeling

## Draft 5

### Title

Data model: domain packs and asset taxonomy expansion for cross-site reuse

### Why now

The BRD expects broader asset-class and domain-aware behavior than the current generalized schemas provide. The current stack improves fleet context, but it does not yet establish a first-class domain-pack model for reuse across plants and asset classes.

### Scope

- Define asset-class and domain-pack metadata as first-class concepts
- Support reusable playbooks, RCA hints, and PM guidance by domain pack
- Carry org, site, and asset-class metadata consistently through context and triage paths
- Document how domain-pack defaults can be overridden locally
- Add at least one concrete domain-pack example to prove the model

### Acceptance Criteria

- Domain-pack metadata is represented explicitly rather than as incidental free-form fields
- Asset-class aware guidance can be retrieved and surfaced consistently
- Cross-site reuse is supported without dropping local override capability
- Context and triage paths preserve org, site, and asset-class metadata end to end
- Tests cover at least one domain-pack aware retrieval or recommendation path

### Dependencies and Notes

- This issue is intentionally broader than pure retrieval quality and should align with Draft 2

## Draft 6

### Title

Governance: data lineage, redaction, and operator-facing source quality indicators

### Why now

The BRD calls for stronger governance and explainability around what data enters the RCA and triage flows. The current stack surfaces more evidence, but it does not yet provide enough lineage, redaction, and source quality signaling for production operations.

### Scope

- Record and surface lineage metadata for key RCA and triage inputs
- Add redaction or exclusion rules for sensitive fields before they enter user-facing summaries
- Expose source quality or confidence indicators where data is partial, stale, or inferred
- Document operator expectations for missing or low-quality inputs
- Ensure lineage metadata composes with existing evidence and repair-plan surfaces

### Acceptance Criteria

- RCA and triage outputs can identify their major upstream sources
- Sensitive fields can be excluded or redacted before user-facing output generation
- Operators can distinguish raw evidence from inferred or degraded data
- Documentation covers lineage and redaction policy decisions
- Tests cover at least one redaction path and one lineage exposure path

### Dependencies and Notes

- Complements `#27` audit logging but focuses on source provenance and redaction rather than actor activity