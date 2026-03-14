set -euo pipefail
BRANCH="feature/openclaw-cron-wiring"

git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

mkdir -p scripts outputs logs

# CLI: add rca-test command that triggers a synthetic RCA and prints summary path
python - "$BRANCH" << 'PY'
import io, sys, re, os
p = "maintenance_intelligence/runner/cli.py"
with open(p, "r", encoding="utf-8") as f:
    s = f.read()
if "def rca_test(" in s:
    sys.exit(0)
insert = '''
@app.command()
def rca_test():
    """
    Trigger a synthetic RCA run (event_id = TEST-RCA-<uuid>) and print the run result.
    """
    import uuid, json
    from .config import Settings
    from .core import run
    s = Settings()
    eid = f"TEST-RCA-{uuid.uuid4().hex[:8]}"
    result = run(eid, s)
    # Write a minimal stdout line friendly to cron parsers
    typer.echo(json.dumps({"event_id": eid, **result}))
'''
s = s.rstrip() + insert + "\n"
with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print("UPDATED", p)
PY

# Cron-friendly wrapper script (idempotent write)
cat > scripts/cron_rca_test.sh << 'SH'
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
SH
chmod +x scripts/cron_rca_test.sh

# README: How to wire with OpenClaw cron
cat >> README.md << 'PY'

## OpenClaw Cron Wiring (Scheduled RCA Test)

This repo provides a cron-friendly CLI and wrapper:
- Trigger a synthetic RCA test: `mi-runner rca-test`
- Cron wrapper: `scripts/cron_rca_test.sh` (writes to `logs/cron_rca_test.log` and prints JSON)

Environment:
- `OPENAI_API_KEY` (for GenAI output; otherwise stub text is used)
- Optional:
  - `MI_RUN_SUMMARY_DIR` (default: `outputs`)
  - `MI_CRON_LOG_DIR` (default: `logs`)

Example OpenClaw cron job (JSON):
{
  "action": "add",
  "job": {
    "name": "maintenance-intel-rca-test-hourly",
    "schedule": { "kind": "cron", "expr": "0 * * * *", "tz": "Asia/Kolkata" },
    "payload": {
      "kind": "agentTurn",
      "message": "Reminder: Run scheduled RCA test now (scripts/cron_rca_test.sh). Expect a new run_summary.json in outputs/.",
      "timeoutSeconds": 60
    },
    "sessionTarget": "isolated",
    "enabled": true
  }
}

If your OpenClaw runner can execute shell commands directly, schedule:
`/workspaces/Maintenance-Intelligence/scripts/cron_rca_test.sh`
and tail `logs/cron_rca_test.log`.

The wrapper outputs a single JSON line from `mi-runner rca-test`, which includes the event_id and run_id. The full run summary is stored at `outputs/YYYY-MM-DD/<run_id>.json`.
PY

# Basic test stub (ensures wrapper exists)
cat > tests/test_cron_wrapper_exists.py << 'PY'
import os
def test_cron_script_exists():
    assert os.path.exists("scripts/cron_rca_test.sh")
PY

git add .
git commit -m "feat: OpenClaw cron wiring — CLI rca-test + cron wrapper + README docs"
git push -u origin "$BRANCH"