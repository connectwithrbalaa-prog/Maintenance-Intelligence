# Notification Routing Follow-up

This stacked follow-up extends the thin webhook notification slice with three focused improvements:

## Goals

1. Support richer routing than a single org-to-webhook mapping.
2. Give operators a better delivery history view in the portal.
3. Move edge degraded notifications off the portal read path and into a runtime emitter.

## Proposed Scope

### Routing

- Add route rules by `event_type`, `severity`, `org_id`, and optional `site_id`.
- Support multiple webhook destinations per organization.
- Preserve a default route fallback when no org-specific match exists.
- Keep configuration file or environment driven for this slice.

### Operator delivery history

- Add portal filters for status, severity, event type, and destination.
- Expose recent delivery failures first by default.
- Show delivery error detail and response status code in a denser history table.
- Keep the existing summary card, but back it with a fuller history view.

### Edge runtime emitter

- Emit degraded and offline notifications from runtime connectivity transitions instead of `/api/v1/portal/edge-status` reads.
- Deduplicate on state transitions so repeated offline snapshots do not spam downstream channels.
- Preserve the portal endpoint as a read-only view over recent delivery records.

## Acceptance Targets

- At least one event type can route to more than one destination.
- Operators can filter recent deliveries in the portal without leaving the page.
- Edge degraded notifications can fire without any portal request.
- Focused tests cover routing selection, filtered portal history, and runtime edge emission.

## Expanded Acceptance Checklist

- RCA completion emits a notification event (`rca.completed`) with run and recommendation identifiers.
- PM exception pathways emit notification events (`cmms.exception`) for retryable, queued-offline, and terminal failures.
- Notification delivery supports both webhook and email channels from the same routing model.
- Policy-level suppression can block delivery for scoped event/org/site combinations and logs a `suppressed` record.
- Policy-level escalation can raise severity to `critical` after configurable recent failure thresholds.
- Focused tests validate email channel delivery, suppression/escalation behavior, PM exception emissions, and RCA completion emissions.

## Slice Plan

### Slice 1: Rule-Based Multi-Destination Routing

Deliver richer route matching and fan-out without changing channel types.

- Add ordered routing rules with match keys: `event_type`, `severity`, `org_id`, optional `site_id`.
- Keep a deterministic fallback route when no rule matches.
- Allow one event to emit to multiple webhook destinations.
- Keep config source as env/file and avoid introducing DB-backed route management in this step.

Exit checks:

- Unit tests prove deterministic first-match and fallback behavior.
- Unit tests cover one-to-many fan-out for at least one event type.
- Existing thin-route configs remain backward compatible.

### Slice 2: Operator Delivery History Filtering

Improve day-two operations by making notification history explorable in place.

- Extend portal notification history with filters: `status`, `severity`, `event_type`, `destination`.
- Default sort to recent failures first, then most recent attempts.
- Render error detail and response code in a denser table layout.
- Preserve existing summary cards while backing them with the richer history query.

Exit checks:

- API tests verify server-side filter semantics and sort ordering.
- UI tests verify filter interactions and reset behavior.
- Failure rows expose status code and a readable error field.

### Slice 3: Runtime Edge Emitter + Transition Dedup

Move edge degraded/offline emission to runtime events so alerts are not tied to portal reads.

- Emit notifications on connectivity state transitions from edge runtime.
- Deduplicate repeated snapshots for unchanged degraded/offline state.
- Keep `/api/v1/portal/edge-status` read-only and non-emitting.
- Persist enough recent event metadata to correlate edge transitions with delivery history.

Exit checks:

- Runtime tests verify transition-driven emission and dedup semantics.
- Regression tests confirm portal edge status reads do not emit notifications.
- Delivery history includes runtime-triggered edge events.

## Non-Goals (This Follow-up)

- No organization self-serve route editor in portal.
- No cross-tenant routing model changes outside existing org/site boundaries.

## Suggested Delivery Order

1. Slice 1 (routing correctness first)
2. Slice 3 (runtime emission semantics)
3. Slice 2 (operator UX on top of stabilized event flow)

This order minimizes UX churn by stabilizing event shape and emission cadence before finalizing the history experience.