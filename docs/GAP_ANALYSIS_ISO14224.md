# Gap Analysis: Current Codebase vs ISO 14224 Canonical Platform

## What Exists

| Layer | Built | Maturity |
|-------|-------|----------|
| Event ingestion (Kafka) | Flat events with `asset_id`, `kind`, `severity` | Working, no taxonomy |
| Work orders | WO table with lifecycle timestamps, CMMS handoff | Working |
| CMMS adapters | Mock + Maximo scaffold | Mock functional |
| Signals | `signals` + `signal_rollups`, vibration/temperature | Working |
| RCA / GenAI | OpenAI structured RCA with repair plans | Working |
| RAG | pgvector hybrid retrieval, doc chunk ingestion | Working |
| PM workflow | Proposal → approve → CMMS handoff → audit | Working |
| Outcomes analytics | Acceptance, WO volume, CMMS health | Working |
| PdM scoring | Heuristic early-warning scorer | Working |
| Portal | Oil & Gas vertical SPA | Working |
| Observability | Prometheus, Grafana, health checks | Working |

## What's Missing

### 1. Asset & Equipment Hierarchy (ISO 14224 L1–L8)

Only `asset_id` (flat string) exists. Need 8 hierarchy levels:
- L1 Industry, L2 BusinessUnit, L3 Site, L4 Facility, L5 System
- L6 EquipmentUnit (with ISO class, OEM, criticality)
- L7 SubUnit, L8 Component

### 2. Failure & Event Taxonomy

No failure mode, mechanism, cause, or maintenance action codes.
Need ISO 14224 reference tables and structured FailureEvent entity.

### 3. CMMS Mapping Tables

No SAP PM or Maximo-to-ISO code mapping tables.
Need `sap_failure_code_map` and `maximo_failure_code_map`.

### 4. Module Architecture

Flat structure. Need `core/`, `ingestion/sap_pm|maximo|scada/`, `ai/rag|llm_workflows/`.

### 5. Process & Equipment Templates

No config-driven templates (PF-WELL, PF-SURF, etc.) or equipment families (EF-ROT, EF-STAT, etc.).

### 6. Reliability Analytics

MTBF/MTTR are placeholders. Need proper calculation from failure events with restoration timestamps.

### 7. Multi-Tenancy

`org_id` only on events. Missing from workorders, signals, equipment tables.

### 8. RAG/GenAI ISO Alignment

No ISO taxonomy in RAG index. No structured retrieval for failure history.

## Recommended Phases

### Phase 1: Core Data Model
- Asset hierarchy tables (L3–L8)
- ISO 14224 taxonomy tables
- Canonical FailureEvent schema
- Equipment family configs

### Phase 2: Ingestion Adapters
- SAP PM adapter
- Maximo bidirectional adapter
- SCADA/historian adapter
- Code mapping tables

### Phase 3: Reliability & Analytics
- MTBF/MTTR/Availability calculator
- Downtime tracking
- Multi-tenant queries

### Phase 4: RAG Enhancement
- ISO taxonomy embedding
- Structured retrievers
- ISO-aligned prompts
