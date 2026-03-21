# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Maintenance Intelligence is a Python 3 / FastAPI application for industrial equipment RCA (Root Cause Analysis). It uses Kafka for event streaming and PostgreSQL (pgvector) for persistence. See `README.md` for full architecture details.

### Running services

Infrastructure (Kafka, Zookeeper, PostgreSQL) runs via Docker Compose:

```
docker compose -f docker-compose.dev.yml up -d zookeeper kafka postgres
```

**Host resolution:** The Kafka advertised listener is `kafka:9092`. For the API to connect from the host, add these to `/etc/hosts`:
```
127.0.0.1 kafka
127.0.0.1 postgres
```

Run migrations and start the dev API server:
```
POSTGRES_HOST=localhost KAFKA_BOOTSTRAP_SERVERS=localhost:9092 python3 -m maintenance_intelligence.db.migrate
POSTGRES_HOST=localhost KAFKA_BOOTSTRAP_SERVERS=localhost:9092 MI_RUN_SUMMARY_DIR=outputs MI_DEV_ALLOW_HEADERS=true uvicorn maintenance_intelligence.api.main:app --reload --host 0.0.0.0 --port 8000
```

Setting `MI_DEV_ALLOW_HEADERS=true` enables header-based identity for local dev. Without it, endpoints requiring auth will return 403.

### Lint, test, build

Standard commands are in the `Makefile`:
- **Lint:** `make lint` (runs `ruff check .` and `black --check .`)
- **Test:** `pytest --ignore=tests/test_migration_smoke.py --ignore=tests/e2e` (unit/integration tests; most mock Kafka/PG)
- **Migration smoke test** requires Docker: `pytest tests/test_migration_smoke.py`
- **E2E tests** require Node + Playwright: `npm run test:portal:e2e`

### Gotchas

- The system Python is `python3` (no `python` symlink by default). Some scripts (e.g., `scripts/demo_pm_approval.sh`) expect `python`. Create a symlink: `sudo ln -sf /usr/bin/python3 /usr/bin/python`.
- The `scripts/demo_pm_approval.sh` health-check polls `/api/v1/health`, which does not exist. The actual health endpoint is `/healthz`. The demo flow can be replicated manually via curl (see README PM demo section).
- Deep health check (`/healthz?deep=true`) shows `kafka_lag` as `degraded` due to a `KafkaConfigurationError` about request/session timeout mismatch. This is cosmetic and does not affect functionality.
- `pip install -e .[dev,ops]` installs scripts to `~/.local/bin`. Ensure `~/.local/bin` is on `PATH`.
