# BRD Issue Checklists

These checklists are written to be pasted into GitHub issues [#39](https://github.com/connectwithrbalaa-prog/Maintenance-Intelligence/issues/39) through [#44](https://github.com/connectwithrbalaa-prog/Maintenance-Intelligence/issues/44).

## [#39](https://github.com/connectwithrbalaa-prog/Maintenance-Intelligence/issues/39) Security: production auth, tenant isolation, and scoped RBAC enforcement

Current status summary:

- [x] Explicit auth-mode handling introduced
- [x] Dev-header behavior tightened behind clearer gating
- [x] Scoped identity helpers introduced
- [x] PM org and site checks enforced on key workflow paths
- [x] RCA trigger enforcement aligned with scoped identity behavior
- [ ] Production-grade auth source integrated
- [ ] Org and site scoping enforced consistently across all protected read and write paths
- [ ] Tenant-aware role checks completed for RCA, PM, retry, and admin-only flows
- [ ] Production trust model for forwarded identity fully documented
- [ ] Cross-tenant rejection coverage completed in tests

Close when:

- [ ] Protected routes reject unauthenticated access outside explicit demo or dev modes
- [ ] Cross-tenant access is blocked consistently
- [ ] Docs clearly separate local demo behavior from production auth behavior

## [#40](https://github.com/connectwithrbalaa-prog/Maintenance-Intelligence/issues/40) Platform: governed context cache and prefetch pipeline for RCA and triage

Current status summary:

- [x] Cache behavior introduced for assembled context
- [x] Freshness or TTL metadata surfaced
- [x] Warm or prefetch behavior added for RCA paths
- [x] Cache observability exposed through metrics or health surfaces
- [x] Invalidation tied to context freshness changes
- [ ] Acceptance criteria reviewed explicitly against the current implementation
- [ ] Final closure gaps, if any, resolved

Close when:

- [ ] Frequently accessed assets resolve context from cache on the intended path
- [ ] Cache entries are scoped appropriately
- [ ] Operators can see freshness and cache behavior clearly
- [ ] Tests and docs reflect the final supported cache model

## [#41](https://github.com/connectwithrbalaa-prog/Maintenance-Intelligence/issues/41) Integrations: connector framework expansion beyond Maximo and mock backends

Current status summary:

- [x] Registry-backed CMMS adapter framework implemented
- [x] Shared connector HTTP and parsing helpers extracted
- [x] Shared response translation layer extracted
- [x] Connector discovery metadata exposed via API
- [x] Portal connector catalog added
- [x] SAP PM scaffold added
- [x] ServiceNow scaffold added
- [x] Connector lifecycle normalization implemented
- [x] Connector provenance summaries surfaced in API and portal
- [x] ServiceNow smoke coverage added
- [ ] Final acceptance review completed
- [ ] Remaining hardening or one-more-backend decision resolved

Close when:

- [ ] Connector contract is considered stable and documented
- [ ] Shared retry, error, and status semantics are sufficient for supported backends
- [ ] Supported non-Maximo integration breadth is accepted as meeting issue intent

## [#42](https://github.com/connectwithrbalaa-prog/Maintenance-Intelligence/issues/42) Workflow: notification routing for RCA, approvals, and degraded operating states

Current status summary:

- [ ] Notification triggers defined
- [ ] At least one outbound delivery path implemented
- [ ] Tenant-aware routing configuration implemented
- [ ] Delivery status visible to operators
- [ ] Failure handling and suppression rules documented
- [ ] End-to-end tests added

Close when:

- [ ] RCA, PM exception, connector failure, and degraded-state events can notify through at least one real channel
- [ ] Delivery failures are visible and non-silent

## [#43](https://github.com/connectwithrbalaa-prog/Maintenance-Intelligence/issues/43) Data model: domain packs and asset taxonomy expansion for cross-site reuse

Current status summary:

- [ ] Domain-pack model defined as first-class metadata
- [ ] Asset-class metadata propagated consistently
- [ ] Reusable playbooks or guidance bound to domain packs
- [ ] Local override model documented
- [ ] One concrete domain-pack example implemented
- [ ] Tests added for domain-aware retrieval or recommendation behavior

Close when:

- [ ] Guidance can be reused across sites without losing local override capability
- [ ] Asset and domain metadata persist end to end through context and triage flows

## [#44](https://github.com/connectwithrbalaa-prog/Maintenance-Intelligence/issues/44) Governance: data lineage, redaction, and operator-facing source quality indicators

Current status summary:

- [ ] Lineage metadata recorded for major RCA and triage inputs
- [ ] Sensitive field redaction or exclusion rules implemented
- [ ] Source quality or degraded-data indicators surfaced to operators
- [ ] Policy decisions documented
- [ ] Tests added for lineage exposure and redaction behavior

Close when:

- [ ] Operators can distinguish raw evidence from inferred or degraded data
- [ ] Sensitive inputs can be excluded before user-facing generation paths
- [ ] Major outputs can identify their upstream source lineage