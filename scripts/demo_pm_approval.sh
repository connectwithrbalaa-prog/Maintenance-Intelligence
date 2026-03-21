#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export MI_DEV_ALLOW_HEADERS="${MI_DEV_ALLOW_HEADERS:-true}"
API_URL="${API_URL:-http://127.0.0.1:8000}"
DEMO_PM_START_API="${DEMO_PM_START_API:-true}"
RUN_SUMMARY_DIR="${MI_RUN_SUMMARY_DIR:-outputs}"
DEMO_PM_RUN_ID="${DEMO_PM_RUN_ID:-}"

usage() {
  cat <<'EOF'
Usage: demo_pm_approval.sh [--use-existing-api] [--api-url URL] [--run-id RUN_ID]

Options:
  --use-existing-api  Skip starting uvicorn and use the API already running at API_URL.
  --api-url URL       Base URL for the API. Default: http://127.0.0.1:8000
  --run-id RUN_ID     Use an existing RCA run summary instead of creating a demo one.

Environment:
  API_URL             Base URL for the API.
  DEMO_PM_START_API   true to start uvicorn locally, false to use an existing API.
  DEMO_PM_RUN_ID      Existing RCA run id to use for proposal generation.
  MI_RUN_SUMMARY_DIR  Directory containing run summaries. Defaults to outputs.
  MI_DEV_ALLOW_HEADERS Defaults to true for local header-based identity.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --use-existing-api)
      DEMO_PM_START_API="false"
      shift
      ;;
    --api-url)
      API_URL="$2"
      shift 2
      ;;
    --run-id)
      DEMO_PM_RUN_ID="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

pretty_print_json() {
  if command -v jq >/dev/null 2>&1; then
    jq .
    return
  fi

  if command -v python >/dev/null 2>&1; then
    python -m json.tool
    return
  fi

  cat
}

uvicorn_bind() {
  python - "$API_URL" <<'PY'
from urllib.parse import urlparse
import sys

parsed = urlparse(sys.argv[1])
host = parsed.hostname or "127.0.0.1"
port = parsed.port or (443 if parsed.scheme == "https" else 80)
print(host)
print(port)
PY
}

create_demo_run_summary() {
  python - "$RUN_SUMMARY_DIR" <<'PY'
import datetime as dt
import json
import sys
import uuid
from pathlib import Path

root = Path(sys.argv[1]).expanduser()
run_id = f"DEMO-PM-{uuid.uuid4().hex[:8]}"
date_dir = root / dt.datetime.utcnow().strftime("%Y-%m-%d")
date_dir.mkdir(parents=True, exist_ok=True)
path = date_dir / f"{run_id}.json"
payload = {
    "run_id": run_id,
    "status": "ok",
    "recommendation_id": run_id,
    "event_id": "DEMO-EVT-001",
    "model": {"name": "demo-script", "version": "local", "confidence": 0.82},
    "structured": {
        "title": "Inspect vibration excursion on PUMP-101",
        "hypothesis": [
            "Repeated vibration anomalies were detected alongside elevated temperature readings.",
        ],
        "immediate_actions": [
            "Inspect bearings and confirm lubrication condition during the next maintenance window.",
        ],
        "pm_suggestions": [
            "Create a planned inspection and bearing check for the next maintenance window.",
        ],
        "confidence": 0.82,
    },
    "context_meta": {"asset_id": "PUMP-101", "event_kind": "anomaly"},
}
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(run_id)
print(path)
PY
}

server_pid=""
created_summary_path=""
cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" >/dev/null 2>&1 || true
    wait "$server_pid" 2>/dev/null || true
  fi

  if [[ -n "$created_summary_path" ]] && [[ -f "$created_summary_path" ]]; then
    rm -f "$created_summary_path"
    rmdir "$(dirname "$created_summary_path")" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ "$DEMO_PM_START_API" == "true" ]]; then
  mapfile -t uvicorn_target < <(uvicorn_bind)
  python -m uvicorn maintenance_intelligence.api.main:app --host "${uvicorn_target[0]}" --port "${uvicorn_target[1]}" >/tmp/mi-demo-pm-approval.log 2>&1 &
  server_pid="$!"
fi

for _ in $(seq 1 30); do
  if curl -fsS "$API_URL/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$API_URL/api/v1/health" >/dev/null 2>&1; then
  if [[ "$DEMO_PM_START_API" == "true" ]]; then
    echo "API did not become ready. See /tmp/mi-demo-pm-approval.log" >&2
  else
    echo "API at $API_URL did not respond to /api/v1/health" >&2
  fi
  exit 1
fi

analysis_payload='{
  "run_id": "__RUN_ID__"
}'

if [[ -z "$DEMO_PM_RUN_ID" ]]; then
  mapfile -t demo_summary < <(create_demo_run_summary)
  DEMO_PM_RUN_ID="${demo_summary[0]}"
  created_summary_path="${demo_summary[1]}"
fi

analysis_payload="${analysis_payload/__RUN_ID__/$DEMO_PM_RUN_ID}"

proposal_response="$(curl -fsS \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: demo.pm' \
  -H 'X-User-Role: planner' \
  -d "$analysis_payload" \
  "$API_URL/api/v1/agents/pm/advisor/analyze")"

proposal_id="$(printf '%s' "$proposal_response" | python -c 'import json,sys; print(json.load(sys.stdin)["proposal"]["proposal_id"])')"

approve_response="$(curl -fsS \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: demo.pm' \
  -H 'X-User-Role: planner' \
  -d '{"approved_by": "demo.pm"}' \
  "$API_URL/api/v1/agents/pm/proposals/$proposal_id/approve")"

printf 'Created proposal:\n'
printf '%s\n' "$proposal_response" | pretty_print_json
printf '\nApproved proposal:\n'
printf '%s\n' "$approve_response" | pretty_print_json