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
