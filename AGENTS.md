# AGENTS.md

## Cursor Cloud specific instructions

**Skip codebase exploration — this file is the architecture map.**

### Product overview

Maintenance Intelligence is a GenAI-driven preventive/proactive asset maintenance platform for upstream Oil & Gas. It ingests equipment data from CMMS systems (SAP PM, IBM Maximo) and SCADA/historians, normalizes everything into an ISO 14224–aligned canonical model, and provides RCA (Root Cause Analysis), reliability analytics, and RAG-based GenAI recommendations.

**Current vertical**: Oil & Gas (compressor trains, pump skids, gas turbines).
**Portal**: Single-file SPA at `maintenance_intelligence/web/index.html`.

---

### Package architecture

```
maintenance_intelligence/
├── api/                          # FastAPI routers (~60 endpoints)
│   ├── main.py                   # App entry, all router registration
│   ├── hierarchy.py              # ISO 14224 hierarchy CRUD (L3–L8)
│   ├── taxonomy.py               # ISO failure modes, equipment families, process templates
│   ├── failure_events.py         # Canonical failure events CRUD
│   ├── reliability.py            # MTBF, MTTR, availability endpoints
│   ├── rag_context.py            # Structured RAG context retrieval
│   ├── portal.py                 # Portal UI + run summary endpoints
│   ├── pm_advisor.py             # PM proposal analyze/approve/history
│   ├── reports.py                # Bad-actors, prioritized assets
│   ├── outcomes.py               # RCA outcomes analytics
│   ├── feedback.py               # Operator feedback submit/list
│   ├── signals.py                # Signal summary for assets
│   ├── repair_plan.py            # Repair plan CRUD
│   ├── health.py                 # /healthz (shallow + deep)
│   ├── identity.py               # /whoami
│   ├── metrics.py                # Prometheus /metrics
│   ├── otel.py                   # OpenTelemetry init
│   └── middleware/identity.py    # Auth/scope middleware (dev headers via MI_DEV_ALLOW_HEADERS=true)
│
├── core/                         # ISO 14224 canonical domain layer
│   ├── models/
│   │   ├── hierarchy.py          # Pydantic: Industry, BusinessUnit, Site, Facility, System, EquipmentUnit, SubUnit, Component
│   │   ├── events.py             # Pydantic: FailureEvent, MaintenanceEvent
│   │   └── taxonomy.py           # Pydantic: ISOFailureMode, ISOFailureMechanism, ISOFailureCause, etc.
│   ├── repositories/
│   │   └── hierarchy.py          # DB CRUD: list_sites, get_equipment_unit, get_hierarchy_path, upsert_equipment_unit
│   ├── reliability/
│   │   ├── calculator.py         # Pure functions: calculate_mtbf, calculate_mttr, calculate_availability, calculate_reliability
│   │   └── queries.py            # DB queries: get_equipment_reliability, get_asset_reliability, get_fleet_reliability
│   └── taxonomy/
│       ├── failure_codes.py      # ISO 14224 Annex B seed data (22 modes, 16 mechanisms, 7 causes, 11 actions, 8 detection methods)
│       ├── equipment_families.py # EF-ROT, EF-STAT, EF-ELEC, EF-INST, EF-SAFE, EF-PACK + PF-WELL/SURF/UTIL/PIPE
│       └── seed_pilot_site.py    # Demo Gulf of Mexico site: 18 equipment, 19 sub-units, 16 components, 8 failure events
│
├── ai/                           # GenAI / RAG layer
│   ├── rag/
│   │   └── structured_retriever.py  # get_hierarchy_context, get_failure_history, get_iso_taxonomy_context, assemble_rca_context
│   └── prompts/
│       └── rca_templates.py      # SYSTEM_PROMPT (ISO-aligned), build_rca_prompt, build_pm_optimization_prompt
│
├── ingestion/                    # Source-system adapters (all output canonical dataclasses)
│   ├── base.py                   # ABC: BaseIngestionAdapter + CanonicalEquipment/FailureEvent/WorkOrder/Signal
│   ├── code_mapper.py            # SAP/Maximo code → ISO 14224 translation via DB mapping tables
│   ├── seed_mappings.py          # 28 SAP + 25 Maximo → ISO code mappings (run as script to seed DB)
│   ├── sap_pm/adapter.py         # Equipment master, notifications, orders → canonical
│   ├── maximo/adapter.py         # Assets, WOs, failure reports → canonical (bidirectional)
│   └── scada/adapter.py          # Tag mapping + time-series readings → CanonicalSignal
│
├── cmms/                         # CMMS WO push adapters (write direction)
│   ├── adapter.py                # Base adapter, factory, result normalization
│   ├── maximo.py                 # Maximo OSLC WO creation scaffold
│   └── mock.py                   # Mock adapter for local dev
│
├── genai/gateway.py              # OpenAI structured RCA call (existing, not yet wired to ISO prompts)
├── context/assembler.py          # Legacy context assembly (WOs, signals, doc chunks, RAG)
├── rag/retrieval.py              # Legacy hybrid retrieval (BM25 + pgvector)
├── rag/ingest.py                 # Legacy doc chunk ingestion
│
├── services/                     # Kafka consumers + background services
│   ├── rca_agent.py              # RCA Kafka consumer (event → GenAI → recommendation)
│   ├── ingestion.py              # Event ingestion Kafka consumer
│   ├── wo_bridge.py              # WO handoff Kafka consumer
│   ├── signals.py                # Signal extraction + rollup from events
│   ├── simulator.py              # Synthetic event generator
│   ├── pdm_scorer.py             # PdM early-warning scoring
│   └── repair_plan_service.py    # Repair plan persistence
│
├── runner/                       # CLI, config, orchestration
│   ├── config.py                 # Pydantic Settings (all env vars, pg_dsn, sqlalchemy_url)
│   ├── cli.py                    # Typer CLI (mi-runner)
│   ├── core.py                   # Single-run RCA orchestration
│   ├── edge_agent.py             # Edge RCA with local fallback
│   └── edge_command_buffer.py    # Edge CMMS command queue
│
├── db/alembic/versions/          # 8 Alembic migrations
│   ├── 001_initial.py            # events, workorders, doc_chunks, signals, signal_rollups
│   ├── 002–006                   # pm_proposals, timestamps, rca_feedback, repair_plan
│   ├── 007_iso14224_canonical_model.py  # 16 new tables: hierarchy L1–L8, taxonomy, failure_events, CMMS maps
│   └── 008_add_tenant_id_columns.py    # tenant_id on workorders, signals, signal_rollups
│
└── web/
    ├── index.html                # Portal SPA (~7,000 lines, Oil & Gas vertical)
    └── assets/                   # JS modules (charts.js, notifications.js, domUtils.js, perfMetrics.js)
```

---

### Database tables (26 total)

**Hierarchy (L1–L8):** `industries`, `business_units`, `sites`, `facilities`, `systems`, `equipment_units`, `subunits`, `components`

**ISO taxonomy:** `iso_failure_modes` (22), `iso_failure_mechanisms` (16), `iso_failure_causes` (7), `iso_maintenance_actions` (11), `iso_detection_methods` (8)

**Canonical events:** `failure_events` (ISO-coded with equipment FK, downtime tracking)

**CMMS mapping:** `sap_failure_code_map` (28 rows), `maximo_failure_code_map` (25 rows)

**Original tables:** `events`, `workorders`, `signals`, `signal_rollups`, `doc_chunks`, `pm_proposals`, `rca_feedback`, `repair_plan`, `repair_part`

---

### Key API endpoint groups

| Prefix | Router file | Purpose |
|--------|------------|---------|
| `/api/v1/hierarchy/` | `hierarchy.py` | Sites, facilities, systems, equipment CRUD, hierarchy path |
| `/api/v1/taxonomy/` | `taxonomy.py` | ISO failure modes/mechanisms/causes/actions, equipment families |
| `/api/v1/failure-events/` | `failure_events.py` | Canonical failure event CRUD |
| `/api/v1/reliability/` | `reliability.py` | MTBF, MTTR, availability per equipment/asset/fleet |
| `/api/v1/rag/` | `rag_context.py` | Structured context retrieval for GenAI prompts |
| `/api/v1/portal/` | `portal.py` | Portal UI, run summaries |
| `/api/v1/agents/pm/` | `pm_advisor.py` | PM proposal analyze/approve/history |
| `/api/v1/reports/` | `reports.py`, `outcomes.py` | Bad-actors, prioritized assets, RCA outcomes |
| `/api/v1/rca/feedback` | `feedback.py` | Operator feedback |
| `/api/v1/signals/` | `signals.py` | Signal summary |
| `/healthz` | `health.py` | Health check (deep: PG + Kafka) |
| `/metrics` | `metrics.py` | Prometheus metrics |

---

### Seeded demo data

**Pilot site** (run `python -m maintenance_intelligence.core.taxonomy.seed_pilot_site`):
- GULF-01: offshore platform, 2 facilities, 8 systems, 18 equipment units, 19 sub-units, 16 components
- 8 failure events with ISO codes and downtime (CT-301A, PS-105B, GT-201, PS-301A, V-201, K-401)
- Equipment: Solar Turbines C65 compressors, Flowserve HPX-2000 pumps, GE LM2500 turbines, Cameron separators

**CMMS mappings** (run `python -m maintenance_intelligence.ingestion.seed_mappings`):
- 28 SAP PM catalog → ISO mappings (Object Part, Damage, Cause, Activity)
- 25 Maximo Failure Class → ISO mappings (Problem, Cause, Remedy)

**Portal demo runs** (in `outputs/2026-03-21/`):
- RUN-OG-COMP-001: CT-301A bearing degradation (89% confidence, full repair plan)
- RUN-OG-PUMP-002: PS-105B seal leak (84%)
- RUN-OG-TURB-003: GT-201 combustion imbalance (76%)

---

### Running services

**Infrastructure** (Docker Compose):
```
docker compose -f docker-compose.dev.yml up -d zookeeper kafka postgres
```

**Host resolution** (required for local dev):
```
127.0.0.1 kafka
127.0.0.1 postgres
```
Add to `/etc/hosts`.

**Migrations:**
```
POSTGRES_HOST=localhost python3 -m maintenance_intelligence.db.migrate
```

**API server:**
```
POSTGRES_HOST=localhost KAFKA_BOOTSTRAP_SERVERS=localhost:9092 MI_RUN_SUMMARY_DIR=outputs MI_DEV_ALLOW_HEADERS=true uvicorn maintenance_intelligence.api.main:app --reload --host 0.0.0.0 --port 8000
```

`MI_DEV_ALLOW_HEADERS=true` enables header-based auth. Without it, all authenticated endpoints return 403.

**Seed data:**
```
python -m maintenance_intelligence.core.taxonomy.seed_pilot_site
python -m maintenance_intelligence.ingestion.seed_mappings
```

### Lint, test, build

- **Lint:** `make lint` (ruff + black)
- **Test:** `pytest --ignore=tests/test_migration_smoke.py --ignore=tests/e2e`
- **E2E:** `npm install && npx playwright install --with-deps chromium && npm run test:portal:e2e`
- **237 tests** currently passing

### Gotchas

- System Python is `python3`, not `python`. Create symlink: `sudo ln -sf /usr/bin/python3 /usr/bin/python`
- Demo script `scripts/demo_pm_approval.sh` polls `/api/v1/health` which doesn't exist — use `/healthz` instead
- Deep health check shows `kafka_lag` as degraded (cosmetic KafkaConfigurationError, not functional)
- `pip install -e .[dev,ops]` installs to `~/.local/bin` — ensure it's on PATH
- Portal is Oil & Gas vertical. Section headers use operator language (Probable cause, Planned maintenance, Work order status)

### Docs

- `docs/GAP_ANALYSIS_ISO14224.md` — Full gap analysis vs canonical prompt
- `docs/DEMO_CUSTOMER_PACKET_OIL_GAS.md` — 12-minute O&G demo script
- `docs/DEMO_VERTICAL_CUSTOMIZATION_KIT.md` — Placeholder templates for 5 verticals
- `docs/DEMO_MASTER_INDEX.md` — Index of all 26 demo docs
- `PERFORMANCE.md` — Performance patterns checklist and budgets

### What's NOT yet built

- ISO prompts are not wired into the live RCA agent (`services/rca_agent.py` still uses `genai/gateway.py` with free-form prompts)
- Pharma, Utilities, Manufacturing vertical portals
- Live CMMS connector integration (adapters exist but need real endpoint config)
- Grafana dashboards for reliability metrics
- Hierarchy explorer in the portal UI
