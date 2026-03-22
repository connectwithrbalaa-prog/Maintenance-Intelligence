# Demo Script: CTO / Platform Audience

## Goal
Demonstrate architecture confidence: secure workflow surface, integration posture, observability, and rollout practicality.

## Tone
- Technical but concise
- Risk and control focused
- Deployment-oriented

## 15-Minute Flow

### 1. Architecture Frame (2m)
"This stack ingests canonical events, runs context-aware RCA generation, emits recommendation artifacts, and supports approval/handoff workflows via API and portal."

### 2. Product Workflow First (4m)
- Portal run list and run detail
- PM proposal and handoff state
- Repair-plan snapshot

Talk track:
"We lead with workflow value, then validate reliability and controls."

### 3. Auth and Tenant Controls (3m)
- Explain identity modes and trust model.
- Explain tenant-scoped reads/actions.

Talk track:
"Demo-visible surfaces are authenticated; tenant scope is enforced on key reads and actions. Trusted forwarded-header mode is available for production ingress patterns."

### 4. Observability and Operability (3m)
- Pivot to Grafana dashboards for outcomes and observability.
- Mention health, lag, handoff pressure metrics.

Talk track:
"This gives platform teams operational confidence and change-detection signal as rollout expands."

### 5. Rollout Plan (2m)
"Current state is demo-safe auth on customer-visible paths, with full production hardening checklist already sequenced for the next phase."

### 6. Close (1m)
"The value is a practical path from anomaly intelligence to operational execution with measurable controls."

## CTO Questions

### "How does this fit enterprise auth?"
"Use trusted forwarded headers behind the existing ingress/auth proxy boundary, with demo headers disabled in production."

### "How do you prevent tenant leakage?"
"Tenant checks and filtering are applied on demo-visible reads and action paths; cross-tenant access is denied or not returned."

### "How does this scale operationally?"
"The design separates workflow APIs from observability and uses explicit metrics, lag checks, and dashboard visibility for controlled rollout."

## Close
"The system is positioned for phased adoption: secure demo path now, full enterprise production hardening as the next gated milestone."
