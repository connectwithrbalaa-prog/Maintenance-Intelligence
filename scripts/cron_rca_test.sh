#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LOG_DIR="${MI_CRON_LOG_DIR:-logs}"
OUT_DIR="${MI_RUN_SUMMARY_DIR:-outputs}"
mkdir -p "$LOG_DIR" "$OUT_DIR"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[$TS] START cron_rca_test" >> "$LOG_DIR/cron_rca_test.log"
# Run CLI (ensure venv/Deps are installed in your environment)
RES="$(mi-runner rca-test || true)"
echo "[$TS] RESULT: $RES" >> "$LOG_DIR/cron_rca_test.log"
echo "[$TS] DONE cron_rca_test" >> "$LOG_DIR/cron_rca_test.log"
# Optional: print a short line for external collectors
echo "$RES"
