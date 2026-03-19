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