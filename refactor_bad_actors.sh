set -euo pipefail
BRANCH="feature/bad-actor-dashboard-seed"

git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

mkdir -p maintenance_intelligence/api outputs/reports

# API endpoint
cat > maintenance_intelligence/api/reports.py << 'PY'
from fastapi import APIRouter, Query
from typing import List, Dict, Any
import psycopg2
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

def with_pg(dsn: str):
    import time
    while True:
        try:
            return psycopg2.connect(dsn)
        except Exception:
            time.sleep(1)

@router.get("/bad-actors")
def bad_actors(limit: int = Query(20, ge=1, le=200)) -> List[Dict[str, Any]]:
    """
    Ranks assets by recent event/WO activity (MVP heuristic):
    - score = (#events last 90d) + 2*(#workorders last 90d)
    - latest_severity from most recent event
    """
    s = Settings()
    conn = with_pg(s.pg_dsn)
    try:
        with conn, conn.cursor() as cur:
            # events count (90d)
            cur.execute("""
                SELECT asset_id, COUNT(*) AS ev_count, MAX(occurred_at) AS last_evt_at
                FROM events
                WHERE occurred_at > (NOW() - INTERVAL '90 days')
                GROUP BY asset_id
            """)
            ev = {r[0]: {"ev_count": r[1], "last_evt_at": r[2]} for r in cur.fetchall() if r and r[0]}

            # latest severity per asset
            cur.execute("""
                SELECT DISTINCT ON (asset_id) asset_id, severity, occurred_at
                FROM events
                WHERE occurred_at > (NOW() - INTERVAL '90 days')
                ORDER BY asset_id, occurred_at DESC
            """)
            sev = {r[0]: r[1] for r in cur.fetchall() if r and r[0]}

            # workorder count (90d)
            cur.execute("""
                SELECT asset_id, COUNT(*) AS wo_count
                FROM workorders
                WHERE COALESCE((metadata->>'created_at')::timestamptz, NOW()) > (NOW() - INTERVAL '90 days')
                GROUP BY asset_id
            """)
            wo = {r[0]: r[1] for r in cur.fetchall() if r and r[0]}

        rows = []
        asset_ids = set(ev.keys()) | set(wo.keys())
        for a in asset_ids:
            ec = ev.get(a, {}).get("ev_count", 0)
            wc = wo.get(a, 0)
            score = ec + 2 * wc
            rows.append({
                "asset_id": a,
                "score": int(score),
                "events_90d": int(ec),
                "workorders_90d": int(wc),
                "latest_severity": sev.get(a),
                "last_event_at": ev.get(a, {}).get("last_evt_at"),
            })
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows[:limit]
    finally:
        try: conn.close()
        except Exception: pass
PY

# Mount reports router
if ! grep -q "reports_router" maintenance_intelligence/api/main.py; then
  sed -i '1i from maintenance_intelligence.api.reports import router as reports_router' maintenance_intelligence/api/main.py
  sed -i 's/app = FastAPI.*/&\napp.include_router(reports_router)/' maintenance_intelligence/api/main.py
fi

# CLI exporter
python - "$BRANCH" << 'PY'
import io, sys, os
p = "maintenance_intelligence/runner/cli.py"
with open(p, "r", encoding="utf-8") as f:
    s = f.read()
if "def export_bad_actors(" in s:
    sys.exit(0)
insert = '''
@app.command()
def export_bad_actors(limit: int = 50):
    """
    Export bad-actor ranking as JSON to outputs/reports/bad_actors_<date>.json
    """
    import json, datetime as dt
    from maintenance_intelligence.api.reports import bad_actors
    from maintenance_intelligence.runner.config import Settings
    s = Settings()
    rows = bad_actors(limit=limit)  # FastAPI fn is plain python callable
    outdir = getattr(s, "run_summary_dir", "outputs")
    path_dir = os.path.join(outdir, "reports")
    os.makedirs(path_dir, exist_ok=True)
    fname = f"bad_actors_{dt.datetime.utcnow().strftime('%Y-%m-%d')}.json"
    path = os.path.join(path_dir, fname)
    with open(path, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    typer.echo(path)
'''
s = s.rstrip() + insert + "\n"
with open(p, "w", encoding="utf-8") as f:
    f.write(s)
print("UPDATED", p)
PY

# README doc
cat >> README.md << 'PY'

## Bad Actor Dashboard (Seed)

- API: GET /api/v1/reports/bad-actors?limit=20
  - Score = events_90d + 2*workorders_90d
  - Includes latest_severity and last_event_at (when available)
- CLI export:
  - mi-runner export-bad-actors --limit 50
  - Writes to outputs/reports/bad_actors_<YYYY-MM-DD>.json
PY

# Basic test
cat > tests/test_reports_import.py << 'PY'
def test_reports_import():
    from maintenance_intelligence.api import reports
    assert hasattr(reports, "bad_actors")
PY

git add .
git commit -m "feat: Bad Actor dashboard seed — API endpoint + CLI JSON export"
git push -u origin "$BRANCH"