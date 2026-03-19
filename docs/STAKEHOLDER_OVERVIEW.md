# Maintenance Intelligence Stakeholder Overview

## Executive Summary

Maintenance Intelligence is an industrial operations workflow product that turns equipment events, signals, maintenance history, and knowledge sources into structured RCA outputs, prioritized triage decisions, and governed maintenance handoff workflows.

The product is no longer just an RCA draft generator. The implemented platform now spans:

- event-driven RCA generation
- structured repair planning
- prioritized triage and early-warning scoring
- PM proposal approval and follow-through
- CMMS handoff and connector normalization
- operator portal workflows and diagnostics
- edge buffering, replay, and degraded-mode fallback
- observability, outcomes tracking, and deployment scaffolding

The current branch and follow-up work move the product closer to the BRD target state, but the BRD is not yet fully closed. The main remaining gaps are production auth and tenant isolation, full notification routing, richer domain-pack modeling, and stronger lineage/redaction governance.

## Why This Product

Industrial maintenance teams already have alarms, historians, CMMS systems, and operator knowledge, but these systems are usually fragmented:

- root-cause reasoning is manual and inconsistent
- maintenance prioritization is reactive or spreadsheet-driven
- recommendations are hard to trace from signal to action
- approvals and work-order follow-through are operationally noisy
- degraded or edge environments make cloud-only workflows brittle

Maintenance Intelligence addresses that gap by providing one operational layer that can:

- interpret incoming operational events
- assemble context across signals, work history, and documents
- produce structured RCA and repair guidance
- route maintenance proposals into approval and handoff workflows
- expose operator-ready status, diagnostics, and backlog signals

## Why Now

The timing is favorable for four reasons:

- Plants are under pressure to reduce unplanned downtime without proportionally increasing headcount.
- Existing maintenance data is already available in CMMS, signals, and documents, but not operationalized consistently.
- GenAI is now useful when constrained by structured outputs, retrieval grounding, and governed workflow boundaries.
- Edge and degraded operating conditions require resilient local fallbacks rather than cloud-only assumptions.

This means the product is well positioned as a practical operations layer rather than a speculative AI feature.

## Customer Fit and Purpose

The product fits customers that have:

- recurring asset failures or nuisance alarms
- distributed plant or site operations
- existing CMMS usage but weak handoff visibility
- maintenance backlogs that are hard to prioritize consistently
- a need to improve RCA quality without adding large analyst teams
- mixed connectivity or edge-mode constraints

The product is especially relevant where the customer needs to connect reliability engineering, maintenance planning, and plant operations into one governed workflow.

In customer context, the product serves five purposes:

- reduce time from event to actionable maintenance decision
- improve consistency of RCA and recommended actions
- make PM proposal approval and CMMS handoff observable
- preserve operational continuity in degraded or edge environments
- provide a measurable backbone for maintenance outcomes and operator feedback

## Business Architecture

### Primary Stakeholders

- Operations leaders: need reduced downtime, clearer backlog pressure, and better cross-team visibility
- Reliability engineers: need faster and more consistent RCA outputs
- Maintenance planners and supervisors: need prioritized PM proposals and clean approval workflows
- Plant operators: need understandable portal views, status, and exception visibility
- IT and platform owners: need secure integration boundaries, observability, and deployment control

### Business Capabilities

- Event-to-RCA workflow
- Asset prioritization and triage
- Repair-plan generation and evidence review
- PM proposal analysis, approval, retry, and follow-through
- CMMS handoff normalization across backends
- Outcomes measurement and operator feedback
- Edge resilience and degraded-mode operation

### Operating Model

- Upstream systems generate events, measurements, and work history.
- Maintenance Intelligence assembles context and generates structured recommendations.
- Human approvers validate or reject PM actions.
- Approved actions are handed off to CMMS connectors.
- Operators monitor results, backlog, retries, lifecycle state, and outcomes in the portal and dashboards.

## Technical Architecture

### Core Architecture Pattern

The platform is an event-driven maintenance workflow stack with a service-oriented runtime and a portal/API surface.

### Major Technical Components

- Kafka-based ingestion and service-to-service event flow
- PostgreSQL plus migrations for persistence
- RCA agent with GenAI gateway plus structured fallback behavior
- Context assembler combining work history, signals, and hybrid RAG retrieval
- PM advisor and approval APIs
- CMMS adapter framework with backend discovery and normalized connector lifecycle handling
- Static portal UI backed by FastAPI endpoints
- Prometheus, Grafana, and Alertmanager observability surfaces
- Edge buffering and replay logic for degraded environments

### Current Integration Architecture

- CMMS backends currently supported at contract level: `mock`, `maximo`, `sap_pm`, `servicenow`
- SAP PM and ServiceNow are scaffold integrations proving the connector contract
- The system normalizes connector status, lifecycle phase, and work-order provenance so the portal and APIs remain backend-agnostic

### Deployment and Resilience Model

- local/dev compose stack with API, PostgreSQL, Kafka, Prometheus, Grafana, and Alertmanager
- migration-first startup behavior in dev compose
- deep health and lag-aware health checks
- opt-in edge buffering and replay for ingestion and handoff
- deterministic local RCA fallback when GenAI is unavailable

## Core Workflows

### Workflow 1: Event to RCA

- Operational event is ingested.
- Context is assembled from work history, signals, and RAG sources.
- RCA is generated via GenAI or fallback stub.
- Structured RCA artifact is persisted as a run summary.
- Portal exposes the run for inspection.

### Workflow 2: RCA to PM Proposal

- RCA output produces PM suggestions.
- PM advisor surfaces proposals through API and portal workflows.
- Proposal data includes rationale, confidence, and downstream approval metadata.

### Workflow 3: Approval to CMMS Handoff

- Authorized user approves a PM proposal.
- Proposal is handed off through the CMMS adapter layer.
- Connector response is normalized into lifecycle and provenance fields.
- Work-order state and approval history are persisted and surfaced.

### Workflow 4: Operator Follow-Through

- Operators use the portal to inspect proposal status, retries, handoff history, lifecycle phase, backlog pressure, and connector diagnostics.
- Outcomes and backend pressure can be inspected without switching to raw system logs.

### Workflow 5: Edge and Degraded Operation

- Events and handoff commands can be buffered locally.
- Replay restores workflow continuity when upstream systems recover.
- RCA generation can continue in deterministic fallback mode if GenAI is unavailable.

## Features Delivered So Far

- structured RCA generation with persisted run summaries
- repair-plan persistence and evidence surfacing
- prioritized asset scoring and triage workflows
- PM proposal analysis, approval, retry, and approval audit history
- handoff queue operator UX and follow-through views
- edge diagnostics, buffering, replay, and fallback RCA mode
- outcomes reports, metrics, and Grafana starter dashboards
- CMMS connector registry and discovery endpoint
- SAP PM and ServiceNow connector scaffolds
- normalized connector lifecycle and provenance summaries
- portal connector catalog and reviewer/debug provenance card
- smoke coverage for Maximo and ServiceNow HTTP-path flows

## Qualitative Benefits

- Improves consistency of RCA output and repair guidance
- Reduces manual swivel-chair work between RCA, PM approval, and CMMS handoff
- Gives operators and planners a shared operational view of proposal and work-order progress
- Improves trust in AI-assisted recommendations by surfacing evidence, lifecycle, provenance, and retry behavior
- Makes degraded and edge operation operationally manageable instead of opaque

## Quantitative Benefits

Measured business-value deltas are not yet documented in the repo as production outcomes, so the correct stakeholder position is:

- the platform already instruments operational KPIs
- those KPIs can now be used to prove value in pilots and production

Current measurable platform signals include:

- RCA duration and failure rates
- events ingested and recommendations created
- PM handoff backlog and retry pressure
- approval-to-handoff lead time
- outcomes feedback counts and acceptance trends
- Kafka lag and connector backlog by backend

Expected customer KPI improvements to track after rollout:

- lower mean time from event to recommendation
- lower mean time from approval to CMMS handoff
- reduced PM backlog aging
- lower rate of silently failed or stalled handoffs
- improved recommendation acceptance rate
- reduced analyst effort per RCA case

## BRD Fitment Summary

The delivered product now covers a substantial portion of the BRD operating model:

- structured RCA generation
- triage and prioritization
- PM workflow orchestration
- operator portal visibility
- edge resilience
- observability and outcomes measurement

The main BRD areas still not fully closed are:

- production auth and tenant isolation
- notification routing beyond in-app status views
- richer domain-pack and taxonomy modeling
- stronger lineage, redaction, and source-quality governance

## Key Risks and Open Areas

- current connector expansion is strong but still scaffold-heavy for non-Maximo backends
- production identity and tenant isolation need full completion before broader external rollout
- notification routing is still absent as an end-to-end workflow capability
- lineage and redaction controls need strengthening for production governance expectations

## Recommended Stakeholder Message

Maintenance Intelligence is now a credible maintenance workflow platform rather than a narrow RCA prototype. It already demonstrates event-driven RCA, triage, PM orchestration, CMMS handoff normalization, edge resilience, and operational observability. The remaining BRD work is now concentrated in platform hardening and governance rather than basic product shape.