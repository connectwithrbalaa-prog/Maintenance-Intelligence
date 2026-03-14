set -euo pipefail
BRANCH="feature/config-docs-polish"

git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

mkdir -p scripts

# .env.example
cat > .env.example << 'ENV'
# Core
MI_ENV=dev
MI_LOG_LEVEL=INFO

# Kafka / Postgres
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
POSTGRES_DB=maintenance
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost

# GenAI
OPENAI_API_KEY=replace_me
MI_GENAI_MODEL=gpt-4.1
MI_GENAI_TIMEOUT_S=25

# Outputs / Logs
MI_RUN_SUMMARY_DIR=outputs
MI_CRON_LOG_DIR=logs
ENV

# Makefile
cat > Makefile << 'MK'
.PHONY: setup dev-install fmt lint test api run-sim run-ingest run-rca run-wo export-bad-actors migrate

setup:
\tpython -m pip install --upgrade pip
\tpip install -e .[dev]

dev-install: setup

fmt:
\tblack .
\truff check . --fix

lint:
\truff check .
\tblack --check .

test:
\tpytest

api:
\tuvicorn maintenance_intelligence.api.main:app --reload

run-sim:
\tpython -m maintenance_intelligence.services.simulator

run-ingest:
\tpython -m maintenance_intelligence.services.ingestion

run-rca:
\tpython -m maintenance_intelligence.services.rca_agent

run-wo:
\tpython -m maintenance_intelligence.services.wo_bridge

export-bad-actors:
\tmi-runner export-bad-actors --limit 50

migrate:
\tpython -m maintenance_intelligence.db.migrate
MK

# Dev up/down helpers (placeholders; adjust for your local env/docker-compose if present)
cat > scripts/dev_up.sh << 'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "No docker-compose provided; ensure Kafka and Postgres are up and configured via env:"
echo "- KAFKA_BOOTSTRAP_SERVERS"
echo "- POSTGRES_*"
echo "Then run: make migrate && make api"
SH
chmod +x scripts/dev_up.sh

cat > scripts/dev_down.sh << 'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "No container stack to stop in this repo. If using external Docker, stop those services there."
SH
chmod +x scripts/dev_down.sh

# README: env matrix + quickstart
cat >> README.md << 'MD'

## Configuration (Environment Matrix)

Core:
- MI_ENV (default: dev)
- MI_LOG_LEVEL (default: INFO)

Kafka / Postgres:
- KAFKA_BOOTSTRAP_SERVERS (default: kafka:9092)
- POSTGRES_DB (default: maintenance)
- POSTGRES_USER (default: postgres)
- POSTGRES_PASSWORD (default: postgres)
- POSTGRES_HOST (default: timescaledb)

GenAI:
- OPENAI_API_KEY (required for live GenAI RCA)
- MI_GENAI_MODEL (default: gpt-4.1)
- MI_GENAI_TIMEOUT_S (default: 25)

Outputs / Logs:
- MI_RUN_SUMMARY_DIR (default: outputs)
- MI_CRON_LOG_DIR (default: logs)

Copy .env.example to .env and set values as needed.

## Dev Quickstart

- make dev-install
- make migrate
- make api
- In separate terminals:
  - make run-sim
  - make run-ingest
  - make run-rca
  - make run-wo

Testing:
- make test

Utilities:
- mi-runner rca --event-id E123
- mi-runner rca-test
- mi-runner export-bad-actors --limit 50
- scripts/cron_rca_test.sh (cron-friendly)
MD

git add .
git commit -m "chore: config/docs polish — .env.example, Makefile, dev scripts, README env matrix"
git push -u origin "$BRANCH"