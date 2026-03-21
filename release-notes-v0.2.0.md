# Maintenance Intelligence v0.2.0 — Structured RCA, Signals, Hybrid RAG, Operational Hardening, and Observability

## Highlights

- **RCA: Structured JSON output**
  - title, hypothesis[], evidence_ids[], immediate_actions[], pm_suggestions[], confidence (0..1)
  - Evidence IDs unify signals/doc chunks/WOs; confidence carried in metadata and run summaries

- **Signals: Rollups + anomaly detection**
  - Measurements table + 1h/6h/24h rollups and threshold/z-score anomalies
  - Exposed via /api/v1/signals/summary and included in RCA evidence

- **RAG: Hybrid retrieval with pgvector**
  - IVFFlat index, BM25+vector hybrid ranking, token-aware context budgeting
  - HTML→text ingestion, bulk chunking, adjustable chunk sizes

- **DB/Ops: Hardening**
  - Alembic migrations, graceful shutdown (SIGINT/SIGTERM), exponential backoff for Kafka/DB

- **Health: Kafka lag monitoring**
  - /healthz?deep=true includes consumer group lag; degrades status above threshold

- **Observability: Production-grade monitoring**
  - Prometheus /metrics (RCA runs/errors/duration, ingestion, recommendations, WO drafts, lag gauge)
  - Optional OTEL tracing to Jaeger/Tempo via OTLP
  - Starter Grafana dashboard JSON

- **Dev Experience & Alerts**
  - Compose stack (Kafka, Postgres, API, Prometheus, Grafana, Alertmanager)
  - Prometheus alert rules for ingestion availability, RCA latency, error rate, and Kafka lag

## Upgrade notes

- Apply Alembic migrations before service start
- Set OPENAI_API_KEY for live RCA
- Expose /metrics for Prometheus
- Configure Alertmanager receivers for real notifications

## Quickstart

- pip install -e .[dev]
- alembic upgrade head
- make api; then start services (sim/ingest/rca/wo)
- Optional: docker compose -f docker-compose.dev.yml up -d (for local monitoring stack)
- Validate: /healthz, /healthz?deep=true, RCA run_summary artifacts, Grafana panels, alert rules firing in Prometheus