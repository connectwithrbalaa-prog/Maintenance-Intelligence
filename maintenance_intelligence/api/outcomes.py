from fastapi import APIRouter, HTTPException, Query, Response
from typing import Dict, Any, List
import io, csv, datetime as dt
import psycopg2
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

def with_pg(dsn: str):
    import time
    last_error = None
    for _ in range(3):
        try:
            return psycopg2.connect(dsn, connect_timeout=2)
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise last_error

def _window_clause(days: int) -> str:
    return f"(NOW() - INTERVAL '{int(days)} days')"

@router.get("/rca-outcomes")
def rca_outcomes(window: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    if window > 365:
        raise HTTPException(status_code=400, detail="Window cannot exceed 365 days")
    s = Settings()
    try:
        conn = with_pg(s.pg_dsn)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
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

            cur.execute(f"""
                SELECT w.wo_id,
                       COALESCE((w.metadata->>'resolved_at')::timestamptz, (w.metadata->>'created_at')::timestamptz) AS wo_ts,
                       e.occurred_at AS rec_ts,
                       w.asset_id
                FROM workorders w
                JOIN events e
                  ON e.event_id = ANY(string_to_array(COALESCE(w.metadata->>'evidence_event_id', ''), ','))
                  OR e.asset_id = w.asset_id
                WHERE COALESCE((w.metadata->>'created_at')::timestamptz, NOW()) > {_window_clause(window)}
                LIMIT 500
            """)
            ttrs: List[float] = []
            for row in cur.fetchall() or []:
                wo_ts, rec_ts = row[1], row[2]
                if wo_ts and rec_ts:
                    delta = (wo_ts - rec_ts).total_seconds()
                    if delta >= 0:
                        ttrs.append(delta)
            out["ttr_seconds_avg"] = (sum(ttrs) / len(ttrs)) if ttrs else None

            cur.execute(f"""
                SELECT w.asset_id, COUNT(*) AS n
                FROM workorders w
                WHERE COALESCE((w.metadata->>'created_at')::timestamptz, NOW()) > {_window_clause(window)}
                GROUP BY w.asset_id
                ORDER BY n DESC
                LIMIT 10
            """)
            out["top_assets_by_wo_volume"] = [{"asset_id": r[0], "count": int(r[1])} for r in cur.fetchall() if r]

        try:
            with conn, conn.cursor() as cur2:
                cur2.execute(f"""
                    SELECT asset_id,
                           COUNT(*) FILTER (WHERE action = 'accept') AS accept_cnt,
                           COUNT(*) AS total_cnt
                    FROM rca_feedback
                    WHERE created_at > {_window_clause(window)}
                    GROUP BY asset_id
                """)
                rows = cur2.fetchall() or []
                out["per_asset_acceptance"] = [
                    {
                        "asset_id": row[0],
                        "acceptance_rate": (int(row[1] or 0) / int(row[2] or 0)) if int(row[2] or 0) > 0 else None,
                        "accepts": int(row[1] or 0),
                        "total": int(row[2] or 0),
                    }
                    for row in rows
                ]
        except Exception:
            out["per_asset_acceptance"] = None

        try:
            with conn, conn.cursor() as cur3:
                cur3.execute(f"""
                    SELECT w.asset_id,
                           AVG(
                               EXTRACT(
                                   EPOCH FROM (
                                       COALESCE((w.metadata->>'resolved_at')::timestamptz, (w.metadata->>'created_at')::timestamptz)
                                       - e.occurred_at
                                   )
                               )
                           ) AS ttr_avg
                    FROM workorders w
                    JOIN events e ON e.asset_id = w.asset_id
                    WHERE COALESCE((w.metadata->>'created_at')::timestamptz, NOW()) > {_window_clause(window)}
                    GROUP BY w.asset_id
                    ORDER BY ttr_avg DESC NULLS LAST
                    LIMIT 10
                """)
                rows = cur3.fetchall() or []
                out["per_asset_ttr"] = [
                    {"asset_id": row[0], "ttr_seconds_avg": float(row[1]) if row[1] is not None else None}
                    for row in rows
                ]
        except Exception:
            out["per_asset_ttr"] = None

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
    # Asset highlights as separate rows for easier slicing
    for a in rep.get("top_assets_by_wo_volume") or []:
        rows.append({"metric": f"top_asset_{a['asset_id']}_wo_count", "value": a["count"]})
    for a in rep.get("per_asset_acceptance") or []:
        rows.append({"metric": f"asset_{a['asset_id']}_acceptance_rate", "value": a.get('acceptance_rate')})
    for a in rep.get("per_asset_ttr") or []:
        rows.append({"metric": f"asset_{a['asset_id']}_ttr_seconds_avg", "value": a.get('ttr_seconds_avg')})

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["metric", "value"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv")