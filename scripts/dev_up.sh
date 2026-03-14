#!/usr/bin/env bash
set -euo pipefail
echo "No docker-compose provided; ensure Kafka and Postgres are up and configured via env:"
echo "- KAFKA_BOOTSTRAP_SERVERS"
echo "- POSTGRES_*"
echo "Then run: make migrate && make api"
