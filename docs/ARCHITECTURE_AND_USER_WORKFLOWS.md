# Architecture and User Workflow Diagrams

This document captures the current Maintenance Intelligence operating model in two views:

- a technical architecture workflow showing how data and control move through the platform
- a user workflow showing how operators and maintenance teams interact with the system end to end

These diagrams reflect the implemented core plus the currently active notification-routing slice described in the BRD progress notes.

Deck-ready exports are generated under [docs/diagrams/export](docs/diagrams/export) from the Mermaid sources in [docs/diagrams/src](docs/diagrams/src).

## How to Regenerate Exports

Use the Mermaid source files in [docs/diagrams/src](docs/diagrams/src) and render them into [docs/diagrams/export](docs/diagrams/export).

Reliable local flow used in this workspace:

```bash
mkdir -p /tmp/mermaid-export
npm install --prefix /tmp/mermaid-export --no-package-lock @mermaid-js/mermaid-cli

for name in \
    executive-summary \
    executive-summary-short \
    architecture-workflow \
    user-workflow \
    brd-future-state \
    brd-future-state-short \
    rca-pm-cmms-sequence \
    notification-edge-sequence
do
    /tmp/mermaid-export/node_modules/.bin/mmdc \
        -i "docs/diagrams/src/${name}.mmd" \
        -o "docs/diagrams/export/${name}.svg" \
        -b white -t neutral -w 2200

    /tmp/mermaid-export/node_modules/.bin/mmdc \
        -i "docs/diagrams/src/${name}.mmd" \
        -o "docs/diagrams/export/${name}.png" \
        -b white -t neutral -w 2200 -s 2
done
```

The white background and wider render width are chosen for slide and deck use.

## Diagram Index

| Diagram | Intended audience | Best asset to use |
| --- | --- | --- |
| Executive Summary View | Steering committee, leadership, stakeholder updates | [docs/diagrams/export/executive-summary.png](docs/diagrams/export/executive-summary.png) |
| Executive Summary View, Short Labels | Leadership slides, title-constrained decks, status reviews | [docs/diagrams/export/executive-summary-short.png](docs/diagrams/export/executive-summary-short.png) |
| Architecture Tech Workflow | Engineering, platform, integration, SRE | [docs/diagrams/export/architecture-workflow.svg](docs/diagrams/export/architecture-workflow.svg) |
| User Workflow | Operations, reliability teams, product, enablement | [docs/diagrams/export/user-workflow.png](docs/diagrams/export/user-workflow.png) |
| BRD Future-State View | Product and delivery planning, BRD closeout reviews | [docs/diagrams/export/brd-future-state.png](docs/diagrams/export/brd-future-state.png) |
| BRD Future-State View, Short Labels | Single-slide BRD status and roadmap checkpoints | [docs/diagrams/export/brd-future-state-short.png](docs/diagrams/export/brd-future-state-short.png) |
| RCA to PM to CMMS Sequence | API design reviews, workflow QA, connector discussions | [docs/diagrams/export/rca-pm-cmms-sequence.svg](docs/diagrams/export/rca-pm-cmms-sequence.svg) |
| Notification Routing and Edge Emission Sequence | Notification routing reviews, edge-runtime operations | [docs/diagrams/export/notification-edge-sequence.svg](docs/diagrams/export/notification-edge-sequence.svg) |

## Executive Summary View

Deck-ready assets:

- SVG: [docs/diagrams/export/executive-summary.svg](docs/diagrams/export/executive-summary.svg)
- PNG: [docs/diagrams/export/executive-summary.png](docs/diagrams/export/executive-summary.png)

```mermaid
flowchart LR
    Event[Operational event or asset anomaly] --> Intelligence[Maintenance Intelligence platform]
    Intelligence --> RCA[Structured RCA and evidence review]
    RCA --> Decision[Operator triage and maintenance decision]
    Decision --> PM[PM proposal and approval]
    PM --> CMMS[CMMS handoff and lifecycle tracking]
    CMMS --> Notify[Notifications analytics and monitoring]

    classDef intake fill:#d8f0ff,stroke:#1d4ed8,color:#0f172a,stroke-width:1.5px;
    classDef platform fill:#ecfccb,stroke:#3f6212,color:#1f2937,stroke-width:1.5px;
    classDef decision fill:#fef3c7,stroke:#b45309,color:#1f2937,stroke-width:1.5px;
    classDef downstream fill:#fee2e2,stroke:#b91c1c,color:#1f2937,stroke-width:1.5px;

    class Event intake;
    class Intelligence,RCA platform;
    class Decision,PM decision;
    class CMMS,Notify downstream;
```

Speaker notes for deck reuse:

- This slide gives the full workflow in one visual: event intake, intelligence, decision, execution, and operational feedback.
- Use this as an opening architecture slide before drilling into technical or user-flow specifics.
- Emphasize that the model is operational today, with BRD closeout work focused on hardening and governance.

## Executive Summary View, Short Labels

This variant uses shorter labels for slide titles and tighter deck layouts.

Deck-ready assets:

- SVG: [docs/diagrams/export/executive-summary-short.svg](docs/diagrams/export/executive-summary-short.svg)
- PNG: [docs/diagrams/export/executive-summary-short.png](docs/diagrams/export/executive-summary-short.png)

```mermaid
flowchart LR
    Event[Asset event] --> Platform[MI platform]
    Platform --> RCA[Structured RCA]
    RCA --> Decision[Operator decision]
    Decision --> PM[PM approval]
    PM --> CMMS[CMMS handoff]
    CMMS --> Ops[Ops alerts and analytics]

    classDef intake fill:#d8f0ff,stroke:#1d4ed8,color:#0f172a,stroke-width:1.5px;
    classDef platform fill:#ecfccb,stroke:#3f6212,color:#1f2937,stroke-width:1.5px;
    classDef decision fill:#fef3c7,stroke:#b45309,color:#1f2937,stroke-width:1.5px;
    classDef downstream fill:#fee2e2,stroke:#b91c1c,color:#1f2937,stroke-width:1.5px;

    class Event intake;
    class Platform,RCA platform;
    class Decision,PM decision;
    class CMMS,Ops downstream;
```

Speaker notes for deck reuse:

- This is the compressed executive storyline: detect, analyze, decide, approve, hand off, and monitor.
- Use this variant when slide space is limited or when the audience needs a fast status narrative.
- Pair with the short BRD future-state view to contrast what is live versus what remains.

## Architecture Tech Workflow

Deck-ready assets:

- SVG: [docs/diagrams/export/architecture-workflow.svg](docs/diagrams/export/architecture-workflow.svg)
- PNG: [docs/diagrams/export/architecture-workflow.png](docs/diagrams/export/architecture-workflow.png)

```mermaid
flowchart LR
    subgraph EventSources[Event and Data Sources]
        Sensors[Equipment sensors and alarms]
        Simulator[Simulator and synthetic test events]
        Docs[Maintenance docs and knowledge content]
        WorkHistory[Work order history and CMMS snapshots]
    end

    subgraph Runtime[Platform Runtime]
        Ingestion[Ingestion service]
        Kafka[(Kafka topics)]
        Signals[Signals processor]
        RCA[RCA agent]
        Context[Context assembler]
        Cache[Governed context cache and prefetch]
        RAG[Hybrid RAG retrieval]
        GenAI[GenAI gateway or local fallback]
        Runs[(Run summaries and outputs)]
        PM[PM advisor APIs]
        Bridge[Work order bridge]
        Notify[Notification service]
        API[FastAPI and portal APIs]
        Portal[Portal UI]
        Edge[Edge buffer and runtime state]
        Metrics[Metrics health and outcomes]
    end

    subgraph DataStores[State and Persistence]
        PG[(Postgres and pgvector)]
        Files[(Output and notification logs)]
    end

    subgraph ExternalSystems[External Systems]
        CMMS[CMMS backends: mock, Maximo, SAP PM, ServiceNow]
        Webhooks[Webhook destinations]
        Alerting[Prometheus Grafana Alertmanager]
    end

    Sensors --> Ingestion
    Simulator --> Ingestion
    Ingestion --> Kafka
    Kafka --> Signals
    Kafka --> RCA

    Docs --> RAG
    WorkHistory --> Context
    Signals --> Context
    RAG --> Context
    Cache --> Context
    PG --> Context
    Context --> RCA
    Context --> Cache

    RCA --> GenAI
    GenAI --> RCA
    RCA --> Runs
    RCA --> PG
    Runs --> Files

    Runs --> API
    PG --> API
    API --> Portal

    Portal --> PM
    PM --> Bridge
    Bridge --> CMMS
    Bridge --> PG
    CMMS --> Bridge

    PM --> Notify
    RCA --> Notify
    Edge --> Notify
    Notify --> Files
    Notify --> API
    Notify --> Webhooks

    Edge --> Bridge
    Edge --> Metrics
    API --> Metrics
    PG --> Metrics
    Metrics --> Alerting
    API --> Portal

    classDef source fill:#d8f0ff,stroke:#1d4ed8,color:#0f172a,stroke-width:1.5px;
    classDef runtime fill:#ecfccb,stroke:#3f6212,color:#1f2937,stroke-width:1.5px;
    classDef storage fill:#ede9fe,stroke:#6d28d9,color:#1f2937,stroke-width:1.5px;
    classDef external fill:#fee2e2,stroke:#b91c1c,color:#1f2937,stroke-width:1.5px;

    class Sensors,Simulator,Docs,WorkHistory source;
    class Ingestion,Kafka,Signals,RCA,Context,Cache,RAG,GenAI,Runs,PM,Bridge,Notify,API,Portal,Edge,Metrics runtime;
    class PG,Files storage;
    class CMMS,Webhooks,Alerting external;
```

## User Workflow

Deck-ready assets:

- SVG: [docs/diagrams/export/user-workflow.svg](docs/diagrams/export/user-workflow.svg)
- PNG: [docs/diagrams/export/user-workflow.png](docs/diagrams/export/user-workflow.png)

```mermaid
flowchart TD
    Start([Asset issue or abnormal event detected]) --> Detect[Event ingested and RCA run created]
    Detect --> Review[Operator opens portal and reviews RCA summary]
    Review --> Evidence[Inspect evidence context signals history and recommendations]
    Evidence --> Decision{Is action needed now?}

    Decision -->|No immediate action| Monitor[Keep under observation and track status in portal]
    Decision -->|Yes| Triage[Triage issue and assess urgency]

    Triage --> PMDecision{Needs preventive or corrective work order?}
    PMDecision -->|No| LocalAction[Execute local mitigation or continue monitoring]
    PMDecision -->|Yes| Proposal[Create or review PM proposal]

    Proposal --> Approval{Approve proposal?}
    Approval -->|No| Rework[Revise recommendation add notes or defer]
    Approval -->|Yes| Handoff[Submit handoff to CMMS connector]

    Handoff --> HandoffResult{Handoff successful?}
    HandoffResult -->|Yes| Track[Track work order status lifecycle and provenance in portal]
    HandoffResult -->|Retryable failure| Retry[Retry queue or admin retry flow]
    HandoffResult -->|Offline or degraded| EdgeQueue[Queue through edge buffer and replay later]
    HandoffResult -->|Terminal failure| Exception[Operator investigates connector failure]

    Retry --> Handoff
    EdgeQueue --> Replay[Replay when connectivity returns]
    Replay --> Handoff
    Exception --> Handoff

    Track --> NotifyOps[Operators receive routed notifications for key events and degraded states]
    Monitor --> NotifyOps
    LocalAction --> NotifyOps

    NotifyOps --> Analytics[Review outcomes dashboards delivery history and operational alerts]
    Analytics --> End([Workflow closed or kept under continuous monitoring])

    classDef startend fill:#d8f0ff,stroke:#1d4ed8,color:#0f172a,stroke-width:1.5px;
    classDef action fill:#ecfccb,stroke:#3f6212,color:#1f2937,stroke-width:1.5px;
    classDef decision fill:#fef3c7,stroke:#b45309,color:#1f2937,stroke-width:1.5px;
    classDef exception fill:#fee2e2,stroke:#b91c1c,color:#1f2937,stroke-width:1.5px;

    class Start,End startend;
    class Detect,Review,Evidence,Monitor,Triage,Proposal,Handoff,Track,NotifyOps,Analytics,LocalAction,Rework,Retry,EdgeQueue,Replay action;
    class Decision,PMDecision,Approval,HandoffResult decision;
    class Exception exception;
```

## BRD Future-State View

This view separates the capabilities that are already delivered from the remaining BRD closeout work.

Deck-ready assets:

- SVG: [docs/diagrams/export/brd-future-state.svg](docs/diagrams/export/brd-future-state.svg)
- PNG: [docs/diagrams/export/brd-future-state.png](docs/diagrams/export/brd-future-state.png)

```mermaid
flowchart LR
    subgraph ImplementedNow[Implemented Now]
        A1[Event driven RCA pipeline]
        A2[Context assembly with signals and hybrid RAG]
        A3[Structured RCA outputs and run summaries]
        A4[PM proposal analysis and approval APIs]
        A5[Connector framework with Maximo SAP PM and ServiceNow scaffolds]
        A6[Portal visibility notifications slice edge replay and observability]
    end

    subgraph PendingBRD[Pending BRD Closure Work]
        B1[Production auth tenant isolation and scoped RBAC]
        B2[Final acceptance and closure for governed cache pipeline]
        B3[Final hardening and acceptance for connector framework]
        B4[Broader notification triggers more channels suppression and escalation]
        B5[Domain packs asset taxonomy and reusable guidance]
        B6[Lineage redaction and source quality indicators]
    end

    A1 --> A2 --> A3 --> A4 --> A5 --> A6
    A2 -. enables .-> B5
    A3 -. requires governance .-> B6
    A4 -. depends on .-> B1
    A5 -. closeout .-> B3
    A6 -. extend .-> B4
    A2 -. closeout .-> B2

    classDef implemented fill:#dcfce7,stroke:#166534,color:#1f2937,stroke-width:1.5px;
    classDef pending fill:#fee2e2,stroke:#b91c1c,color:#1f2937,stroke-width:1.5px;

    class A1,A2,A3,A4,A5,A6 implemented;
    class B1,B2,B3,B4,B5,B6 pending;
```

## BRD Future-State View, Short Labels

This variant compresses the BRD labels for slide-heavy presentations.

Deck-ready assets:

- SVG: [docs/diagrams/export/brd-future-state-short.svg](docs/diagrams/export/brd-future-state-short.svg)
- PNG: [docs/diagrams/export/brd-future-state-short.png](docs/diagrams/export/brd-future-state-short.png)

```mermaid
flowchart LR
    subgraph Live[Implemented]
        A1[RCA pipeline]
        A2[Context and RAG]
        A3[PM workflow]
        A4[Connector layer]
        A5[Portal and alerts]
    end

    subgraph Next[Pending BRD]
        B1[Auth and RBAC]
        B2[Cache closeout]
        B3[Connector hardening]
        B4[Notification expansion]
        B5[Domain packs]
        B6[Lineage and redaction]
    end

    A1 --> A2 --> A3 --> A4 --> A5
    A3 -.-> B1
    A2 -.-> B2
    A4 -.-> B3
    A5 -.-> B4
    A2 -.-> B5
    A1 -.-> B6

    classDef implemented fill:#dcfce7,stroke:#166534,color:#1f2937,stroke-width:1.5px;
    classDef pending fill:#fee2e2,stroke:#b91c1c,color:#1f2937,stroke-width:1.5px;

    class A1,A2,A3,A4,A5 implemented;
    class B1,B2,B3,B4,B5,B6 pending;
```

One-slide summary note (implemented vs pending BRD):

- Implemented now: RCA pipeline, governed context and RAG foundations, PM workflow, connector framework baseline, and portal-plus-alert visibility.
- Pending BRD closeout: production auth and RBAC hardening, cache and connector acceptance closure, broader notification policy and channels, domain packs, and lineage-redaction controls.
- Suggested talk track: "Core workflow is production-shaped; remaining BRD work is concentrated in security, governance, and delivery hardening."

## RCA to PM to CMMS Sequence

This sequence shows the operator-driven approval path, including success, retry, and offline replay outcomes.

Deck-ready assets:

- SVG: [docs/diagrams/export/rca-pm-cmms-sequence.svg](docs/diagrams/export/rca-pm-cmms-sequence.svg)
- PNG: [docs/diagrams/export/rca-pm-cmms-sequence.png](docs/diagrams/export/rca-pm-cmms-sequence.png)

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant Portal as Portal UI or API
    participant RCA as RCA Agent
    participant Context as Context Assembler
    participant PM as PM Advisor API
    participant Bridge as Work Order Bridge
    participant CMMS as CMMS Adapter
    participant Notify as Notification Service
    participant Edge as Edge Buffer

    Operator->>Portal: Open RCA run and inspect recommendation
    Portal->>RCA: Request run summary and structured RCA
    RCA->>Context: Load evidence context for asset and event
    Context-->>RCA: Signals history work orders RAG context cache metadata
    RCA-->>Portal: RCA summary actions confidence and PM suggestions

    Operator->>Portal: Request PM proposal from run
    Portal->>PM: Analyze RCA and create proposal
    PM-->>Portal: Proposal with approval decision data

    Operator->>Portal: Approve proposal
    Portal->>PM: Approve proposal request
    PM->>Bridge: Create or update work order handoff

    alt CMMS available
        Bridge->>CMMS: Submit normalized work order payload
        CMMS-->>Bridge: Work order id lifecycle state provenance
        Bridge-->>PM: Handoff success state
        PM->>Notify: Emit approval or handoff notification
        PM-->>Portal: Approved with connector status
        Notify-->>Portal: Delivery history available to operator
    else Retryable connector failure
        Bridge-->>PM: Retry required or admin retry state
        PM->>Notify: Emit PM exception notification
        PM-->>Portal: Proposal remains visible with retry status
    else Offline or edge degraded
        Bridge->>Edge: Queue command for replay
        Edge-->>Bridge: Stored for later replay
        Bridge-->>PM: queued-offline status
        PM->>Notify: Emit degraded or offline notification
        PM-->>Portal: Show queued offline handoff state
        Edge->>CMMS: Replay when connectivity returns
        CMMS-->>Edge: Replayed work order accepted
    end
```

Speaker notes for deck reuse:

- This sequence is the core execution path from RCA review to approved CMMS handoff.
- Walk the audience through the three operational outcomes: success, retry-required, and queued-offline replay.
- Highlight that operator visibility remains continuous through portal status and notification history.

## Notification Routing and Edge Emission Sequence

This sequence focuses on edge degraded-state emission, route matching, delivery logging, and operator review.

Deck-ready assets:

- SVG: [docs/diagrams/export/notification-edge-sequence.svg](docs/diagrams/export/notification-edge-sequence.svg)
- PNG: [docs/diagrams/export/notification-edge-sequence.png](docs/diagrams/export/notification-edge-sequence.png)

```mermaid
sequenceDiagram
    autonumber
    participant Edge as Edge Runtime
    participant Portal as Portal API
    participant Notify as Notification Service
    participant Routes as Route Matcher
    participant Log as Delivery History
    participant Webhook as Webhook Destinations
    actor Operator

    Edge->>Edge: Detect connectivity degraded or offline transition
    Edge->>Notify: Emit edge state event
    Notify->>Routes: Match by event type severity org and site
    Routes-->>Notify: Return destinations and fallback route
    Notify->>Webhook: Fan out webhook deliveries
    Webhook-->>Notify: Success or failure response
    Notify->>Log: Persist attempt route edge-state and correlation data

    Operator->>Portal: Open notification history
    Portal->>Log: Query filtered recent deliveries
    Log-->>Portal: Return delivery history and edge event metadata
    Portal-->>Operator: Show delivery status failures and route context

    Note over Portal,Notify: Portal history reads are read-only and do not emit new notifications
```

Speaker notes for deck reuse:

- This sequence clarifies that notifications are emitted by runtime transitions, not by portal page loads.
- Emphasize route matching plus fan-out delivery as the mechanism for reliable org and site specific alerting.
- Use this slide to explain traceability: every attempt is persisted with route, edge-state, and correlation context.

## Reading Notes

- The architecture diagram emphasizes the implemented runtime: ingestion, Kafka-driven RCA, context assembly, PM handoff, notifications, edge buffering, and observability.
- The user workflow centers on the operator and maintenance decision path rather than internal service boundaries.
- The executive view is simplified for BRD reviews, steering updates, and stakeholder discussions that do not need service-level detail.
- The short-label variants are intended for slide titles, narrower deck columns, and screenshot-based summaries.
- The future-state view separates implemented platform depth from the remaining BRD closure items.
- The sequence diagram focuses on the approval-to-handoff path because it is the most operationally sensitive workflow in the current system.
- The notification sequence isolates the runtime edge-event emission path from the portal history read path, which matches the current notification-routing design.
- Notification routing is shown as part of the workflow because the current BRD update treats it as active progress rather than a purely future capability.
- Security hardening, broader auth integration, lineage, redaction, and domain packs remain BRD follow-up items and are not shown as closed capabilities.