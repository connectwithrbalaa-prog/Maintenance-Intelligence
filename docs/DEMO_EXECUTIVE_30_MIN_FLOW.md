# 30-Minute Executive Demo Flow

## Audience
Mixed maintenance leadership plus CTO/platform stakeholders.

## Outcome Goal
Show product value, execution control, and rollout confidence in one session.

## Agenda (30 Minutes)
1. Business framing and target outcomes (3 min)
2. Product workflow in portal (12 min)
3. Control model: auth, tenancy, audit trail (5 min)
4. Operational confidence: outcomes and observability (6 min)
5. Pilot proposal and decision ask (4 min)

## Detailed Runbook

### 0:00 to 3:00 - Business Framing
- Problem: decision latency from anomaly to action.
- Target outcomes: faster triage, higher acceptance quality, clearer execution traceability.

Talk track:
"Today we will focus on the workflow and measurable outcomes, then show the controls that make rollout safe."

### 3:00 to 15:00 - Product Workflow (Portal)
- Open run list and select a representative run.
- Show hypothesis, confidence, immediate actions, PM suggestions.
- Show proposal status and handoff progression.
- Show repair-plan details and parts snapshot.
- Show prioritized assets and outcomes summary.

Talk track:
"This is the operator-to-planner path: decision context, action recommendation, approval, and follow-through in one connected flow."

### 15:00 to 20:00 - Control Model
- Explain authenticated identity and tenant scope in demo path.
- Explain role-aware approval behavior and auditability.

Talk track:
"Customer-visible surfaces are authenticated and tenant-scoped; cross-tenant access is filtered or denied. Approval actions remain role-aware and traceable."

### 20:00 to 26:00 - Operational Confidence
- Open outcomes trend view and key handoff metrics.
- Optional pivot to Grafana for observability evidence.

Talk track:
"This shows the system is not only useful in workflow, but measurable and operable over time."

### 26:00 to 30:00 - Pilot Ask
- Pilot scope: one org/site and one critical asset class.
- Timeline: 2-to-4 weeks to validate KPIs.
- KPI set: triage cycle time, recommendation acceptance, follow-through completion.

Talk track:
"The recommended next step is a focused pilot to validate measurable impact before wider rollout."

## Live Demo Guardrails
- Keep one identity and one org throughout the session.
- Use known-good run id and asset id.
- Avoid switching to deep technical debugging during executive time.

## Backup Path (if data is sparse)
1. Show one known-good run detail.
2. Show approval and repair-plan snapshot.
3. Show outcomes summary.
4. Conclude with pilot ask and follow-up technical deep dive.

## Decision Ask
"Approve a constrained pilot with one site and one asset class, with agreed KPI baselines and a 2-to-4-week review checkpoint."
