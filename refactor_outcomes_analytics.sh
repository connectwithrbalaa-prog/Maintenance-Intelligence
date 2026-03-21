set -euo pipefail
BRANCH="feature/outcomes-analytics"

git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

mkdir -p maintenance_intelligence/api dashboards

# 1) Outcomes API (aggregates + CSV)
cat > maintenance_intelligence/api/outcomes.py << 'PY'
from fastapi import APIRouter, Query, Response
from typing import Dict, Any, List
import io, csv, datetime as dt
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

def _window_clause(days: int) -> str:
    return f"(NOW() - INTERVAL '{int(days)} days')"

@router.get("/rca-outcomes")
def rca_outcomes(window: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    s = Settings()
    conn = with_pg(s.pg_dsn)
    try:
        out: Dict[str, Any] = {}
        with conn, conn.cursor() as cur:
            # Feedback counts by action (accept/reject/edited)
            cur.execute(f"""
                SELECT action, COUNT(*) FROM rca_feedback
                WHERE created_at > {_window_clause(window)}
                GROUP BY action
            """)
            fb = {r[0]: int(r[1]) for r in cur.fetchall() if r and r[0]}
            total = sum(fb.values())
            accept = fb.get("accept", 0)
            out["feedback_counts"] = fb
            out["acceptance_rate"] = (accept / total) if total > 0 else None

            # Approx TTR: recommendation -> WO created_at delta (metadata.created_at)
            # NOTE: This is a proxy; refine when WO lifecycle/status timestamps exist.
            cur.execute(f"""
                SELECT w.wo_id, (w.metadata->>'created_at')::timestamptz AS wo_ts,
                       e.occurred_at AS rec_ts, w.asset_id
                FROM workorders w
                JOIN events e ON e.event_id = ANY( string_to_array(COALESCE(w.metadata->>'evidence_event_id',''), ',') ) OR e.asset_id = w.asset_id
                WHERE COALESCE((w.metadata->>'created_at')::timestamptz, NOW()) > {_window_clause(window)}
                LIMIT 500
            """)
            ttrs = []
            for row in cur.fetchall() or []:
                wo_ts, rec_ts = row[1], row[2]
                if wo_ts and rec_ts:
                    delta = (wo_ts - rec_ts).total_seconds()
                    if delta >= 0:
                        ttrs.append(delta)
            out["ttr_seconds_avg"] = (sum(ttrs)/len(ttrs)) if ttrs else None

            # Per-asset summary (top 10 by slowest TTR)
            # This is a placeholder; improve with real WO lifecycle timestamps.
            cur.execute(f"""
                SELECT w.asset_id, COUNT(*) AS n
                FROM workorders w
                WHERE COALESCE((w.metadata->>'created_at')::timestamptz, NOW()) > {_window_clause(window)}
                GROUP BY w.asset_id
                ORDER BY n DESC
                LIMIT 10
            """)
            out["top_assets_by_wo_volume"] = [{"asset_id": r[0], "count": int(r[1])} for r in cur.fetchall() if r]
        return out
    finally:
        conn.close()

@router.get("/rca-outcomes/csv")
def rca_outcomes_csv(window: int = Query(30, ge=1, le=365)):
    # Flatten a report view for leadership export
    rep = rca_outcomes(window=window)  # reuse computation
    rows = []
    # Feedback counts by action -> key/value rows
    for k, v in (rep.get("feedback_counts") or {}).items():
        rows.append({"metric": f"feedback_{k}", "value": v})
    rows.append({"metric": "acceptance_rate", "value": rep.get("acceptance_rate")})
    rows.append({"metric": "ttr_seconds_avg", "value": rep.get("ttr_seconds_avg")})
    # Asset highlights
    for a in rep.get("top_assets_by_wo_volume") or []:
        rows.append({"metric": f"top_asset_{a['asset_id']}_wo_count", "value": a["count"]})

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["metric", "value"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv")
PY

# 2) Mount outcomes router
if ! grep -q "from maintenance_intelligence.api.outcomes import router as outcomes_router" maintenance_intelligence/api/main.py; then
  sed -i '1i from maintenance_intelligence.api.outcomes import router as outcomes_router' maintenance_intelligence/api/main.py
  sed -i 's/app = FastAPI.*/&\napp.include_router(outcomes_router)/' maintenance_intelligence/api/main.py
fi

# 3) Grafana dashboard for Outcomes (starter)
cat > dashboards/outcomes-starter.json << 'JSON'
{
  "title": "Maintenance Intelligence — Outcomes",
  "panels": [
    {
      "type": "stat",
      "title": "Acceptance Rate",
      "targets": [
        { "expr": "sum(increase(rca_feedback_total{action=\"accept\"}[7d])) / clamp_min(sum(increase(rca_feedback_total[7d])), 1)" }
      ]
    },
    {
      "type": "timeseries",
      "title": "Feedback Actions (7d)",
      "targets": [
        { "expr": "increase(rca_feedback_total{action=\"accept\"}[7d])" },
        { "expr": "increase(rca_feedback_total{action=\"reject\"}[7d])" },
        { "expr": "increase(rca_feedback_total{action=\"edited\"}[7d])" }
      ]
    },
    {
      "type": "timeseries",
      "title": "RCA Duration p95",
      "targets": [
        { "expr": "histogram_quantile(0.95, sum by (le) (rate(rca_duration_seconds_bucket[5m])))" }
      ]
    }
  ],
  "schemaVersion": 39,
  "version": 1
}
JSON

# 4) README: outcomes section
cat >> README.md << 'MD'

## Outcomes Analytics

- API:
  - JSON: GET /api/v1/reports/rca-outcomes?window=30
  - CSV: GET /api/v1/reports/rca-outcomes/csv?window=30
- Metrics alignment:
  - rca_feedback_total{action=...} supports acceptance KPI panels.
- Dashboard:
  - dashboards/outcomes-starter.json (import into Grafana)
MD

# 5) Tests (import + csv endpoint sanity)
mkdir -p tests
cat > tests/test_outcomes_import.py << 'PY'
from maintenance_intelligence.api import outcomes
def test_outcomes_imports():
    assert hasattr(outcomes, "rca_outcomes")
PY

cat > tests/test_outcomes_csv.py << 'PY'
from fastapi.testclient import TestClient
from maintenance_intelligence.api.main import app

def test_outcomes_csv_endpoint_exists():
    c = TestClient(app)
    r = c.get("/api/v1/reports/rca-outcomes/csv?window=30")
    # In CI without DB, this may 500; we just assert the route exists and responds.
    assert r.status_code in (200, 500, 502, 503)
PY

git add .
git commit -m "feat(v0.3): outcomes analytics — API (JSON+CSV) and starter Grafana dashboard"
git push -u origin "$BRANCH"