# Stack Reviewer Summaries

Use these messages when sharing the structured RCA stack with reviewers.

## Backend Reviewer DM

Hi, I split the structured RCA branch into a 5-PR stack to keep review scope manageable.

Recommended backend review order:

1. `#33` foundation workflows
2. `#35` RCA and triage intelligence
3. `#36` edge resilience

Key areas for backend review:

- RCA and GenAI integration contracts
- migration and schema safety
- PM retry and idempotency behavior
- scoring and triage semantics
- edge replay and degraded fallback behavior

Tracker: `#38`

## Frontend Reviewer DM

Hi, the structured RCA work is now split into a 5-PR stack.

Recommended frontend review order:

1. `#34` PM follow-through and handoff queue UX
2. `#35` RCA evidence and triage UX
3. `#36` edge diagnostics surfaces

Key areas for frontend review:

- queue views, filters, and summary chips
- empty states and connector-failure handling
- triage drill-through and evidence context presentation
- portal diagnostics for edge buffering and replay

Tracker: `#38`

## Tooling and Docs Reviewer DM

Hi, there is a final docs and tooling PR at the end of the structured RCA stack.

Please review after the product-code PRs:

1. `#37` PR-prep artifacts and stack helper fixes

Focus areas:

- stack helper correctness
- review checklist clarity
- reviewer note usefulness
- single-PR fallback body quality

Tracker: `#38`

## Backend Slack Summary

Backend review ask for the structured RCA stack:

- Start with `#33`, then `#35`, then `#36`
- Focus on RCA contracts, migration safety, PM retry semantics, triage scoring, and edge replay/fallback behavior
- Full stack order and dependencies are tracked in `#38`

## Frontend Slack Summary

Frontend review ask for the structured RCA stack:

- Start with `#34`, then review the UI-facing portions of `#35` and `#36`
- Focus on handoff queue UX, evidence and triage flows, and edge diagnostics surfaces
- Full stack order and dependencies are tracked in `#38`

## Tooling and Docs Slack Summary

Tooling and docs review ask for the structured RCA stack:

- Review `#37` last, after the product-code PRs
- Focus on the stack helper, reviewer docs, and single-PR fallback body
- Full stack order and dependencies are tracked in `#38`