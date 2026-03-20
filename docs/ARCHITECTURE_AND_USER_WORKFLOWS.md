# Architecture and User Workflow Diagrams

This document captures the current Maintenance Intelligence operating model in two views:

- a technical architecture workflow showing how data and control move through the platform
- a user workflow showing how operators and maintenance teams interact with the system end to end

These diagrams reflect the implemented core plus the currently active notification-routing slice described in the BRD progress notes.

Deck-ready exports are generated under [docs/diagrams/export](docs/diagrams/export) from the Mermaid sources in [docs/diagrams/src](docs/diagrams/src).

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

## Reading Notes

- The architecture diagram emphasizes the implemented runtime: ingestion, Kafka-driven RCA, context assembly, PM handoff, notifications, edge buffering, and observability.
- The user workflow centers on the operator and maintenance decision path rather than internal service boundaries.
- The executive view is simplified for BRD reviews, steering updates, and stakeholder discussions that do not need service-level detail.
- The future-state view separates implemented platform depth from the remaining BRD closure items.
- The sequence diagram focuses on the approval-to-handoff path because it is the most operationally sensitive workflow in the current system.
- Notification routing is shown as part of the workflow because the current BRD update treats it as active progress rather than a purely future capability.
- Security hardening, broader auth integration, lineage, redaction, and domain packs remain BRD follow-up items and are not shown as closed capabilities.