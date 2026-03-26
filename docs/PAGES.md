# UI Page Guide

This document describes the current user-facing pages in Oil & Gas Insights and how each page is expected to behave.

## App Shell

The application uses a persistent shell with:

- A top bar titled `Operations Command Center`
- A grouped sidebar for `Intelligence` and `Platform`
- A live health indicator that polls backend health every 30 seconds

The default route redirects to `/runs`.

## AI Runs

Routes:

- `/runs`
- `/runs/:runId`

Purpose:

- Show recent RCA and AI-assisted maintenance runs
- Let operators drill into a run summary and structured recommendations
- Collect user feedback on recommendation quality

Key behavior:

- Lists recent runs with confidence badges
- Opens a detailed run view for the selected record
- Uses a typewriter-style reveal for the summary section
- Displays model metadata when available
- Supports `Accept`, `Reject`, and `Edited` feedback actions
- Falls back to local demo data if the portal API is unavailable

Primary data dependencies:

- `/api/v1/portal/runs`
- `/api/v1/portal/runs/:runId`
- `/api/v1/feedback`

## PM Advisor

Route:

- `/pm-advisor`

Purpose:

- Present preventive maintenance recommendations generated from reliability and RCA context
- Allow a user to approve a selected PM proposal

Key behavior:

- Loads PM proposals from the backend when available
- Falls back to demo proposals if the API is unavailable
- Normalizes proposal confidence into a risk label
- Shows a queue of proposals and a focused detail panel
- Supports approval handoff for the active proposal

Primary data dependencies:

- `/api/v1/agents/pm/proposals`
- `/api/v1/agents/pm/proposals/:id/approve`

## Outcomes

Route:

- `/outcomes`

Purpose:

- Summarize RCA program outcomes and reliability impact
- Visualize avoided downtime, MTBF movement, and bad-actor reduction

Key behavior:

- Loads outcomes analytics and bad-actor data in parallel
- Displays KPI cards for handoffs, acceptance rate, and approval-to-handoff time
- Renders a monthly trend chart and a bad-actor comparison chart
- Falls back to embedded demo series when reporting APIs are unavailable

Primary data dependencies:

- `/api/v1/reports/rca-outcomes`
- `/api/v1/reports/bad-actors`

## System Health

Route:

- `/system-health`

Purpose:

- Show the current state of the backend health surface used by the portal

Key behavior:

- Polls `/healthz?deep=true` every 10 seconds
- Shows aggregate status and individual rows for API gateway, PostgreSQL, and Kafka
- Falls back to a down-state view if the health endpoint cannot be reached

Primary data dependency:

- `/healthz?deep=true`

## Notes And Known Gaps

- The sidebar currently includes a `Signals` navigation item, but the routed app shell in `src/App.tsx` currently wires the primary command-center pages listed above.
- Several pages are designed to degrade gracefully to local demo content if backend services are unavailable.
