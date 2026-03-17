from datetime import datetime
from fastapi import APIRouter, Query, Request
from typing import List, Dict, Any, Optional
import psycopg2
from maintenance_intelligence.api.middleware.identity import require_authenticated_identity
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_SEVERITY_WEIGHTS = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}

_TERMINAL_WORK_ORDER_STATUSES = {"COMP", "COMPLETE", "COMPLETED", "CLOSE", "CLOSED", "DONE"}

_SIGNAL_PERIOD_WEIGHTS = {
    "1h": 3.0,
    "6h": 2.0,
    "24h": 1.0,
}

def with_pg(dsn: str):
    import time
    while True:
        try:
            return psycopg2.connect(dsn)
        except Exception:
            time.sleep(1)


def _window_clause(days: int) -> str:
    return f"(NOW() - INTERVAL '{int(days)} days')"


def _to_isoformat(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z") if value.tzinfo else value.isoformat()
    return value


def _severity_weight(value: Any) -> float:
    if not isinstance(value, str):
        return 0.0
    return _SEVERITY_WEIGHTS.get(value.strip().lower(), 0.0)


def _count_true_flags(anomaly_flags: Any) -> int:
    if not isinstance(anomaly_flags, dict):
        return 0
    return sum(1 for flag in anomaly_flags.values() if bool(flag))


def _signal_anomaly_scores(rows: List[Any]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for row in rows or []:
        if not row or not row[0]:
            continue
        asset_id = str(row[0])
        period = str(row[1]) if row[1] else ""
        weight = _SIGNAL_PERIOD_WEIGHTS.get(period, 1.0)
        scores[asset_id] = scores.get(asset_id, 0.0) + (weight * _count_true_flags(row[2]))
    return scores


def _feedback_summary(rows: List[Any]) -> Dict[str, Dict[str, Optional[float]]]:
    summary: Dict[str, Dict[str, Optional[float]]] = {}
    for row in rows or []:
        if not row or not row[0]:
            continue
        asset_id = str(row[0])
        accept_count = int(row[1] or 0)
        reject_count = int(row[2] or 0)
        decided_total = accept_count + reject_count
        acceptance_rate = (accept_count / decided_total) if decided_total > 0 else None
        summary[asset_id] = {
            "accept_count": accept_count,
            "reject_count": reject_count,
            "acceptance_rate": acceptance_rate,
        }
    return summary


def _asset_mtbf(rows: List[Any]) -> Dict[str, float]:
    last_seen: Dict[str, Any] = {}
    intervals: Dict[str, List[float]] = {}
    for row in rows or []:
        if not row or not row[0] or not row[1]:
            continue
        asset_id = str(row[0])
        event_ts = row[1]
        previous_ts = last_seen.get(asset_id)
        if previous_ts is not None:
            delta = (event_ts - previous_ts).total_seconds()
            if delta >= 0:
                intervals.setdefault(asset_id, []).append(delta)
        last_seen[asset_id] = event_ts
    return {
        asset_id: (sum(values) / len(values))
        for asset_id, values in intervals.items()
        if values
    }


def _mtbf_risk(mtbf_seconds: Optional[float]) -> float:
    if mtbf_seconds is None or mtbf_seconds <= 0:
        return 0.0
    return min(6.0, 86400.0 / mtbf_seconds)


def _feedback_risk(acceptance_rate: Optional[float]) -> float:
    if acceptance_rate is None:
        return 0.0
    return (1.0 - acceptance_rate) * 4.0


def _score_asset(
    *,
    latest_severity: Any,
    event_count: int,
    workorder_count: int,
    open_workorder_count: int,
    signal_anomaly_score: float,
    acceptance_rate: Optional[float],
    mtbf_seconds: Optional[float],
) -> Dict[str, float]:
    components = {
        "severity_risk": _severity_weight(latest_severity) * 2.0,
        "event_volume_risk": float(event_count),
        "workorder_risk": float(workorder_count) + (float(open_workorder_count) * 2.0),
        "signal_risk": float(signal_anomaly_score) * 3.0,
        "feedback_risk": _feedback_risk(acceptance_rate),
        "mtbf_risk": _mtbf_risk(mtbf_seconds),
    }
    components["priority_score"] = round(sum(components.values()), 2)
    return components

@router.get("/bad-actors")
def bad_actors(request: Request, limit: int = Query(20, ge=1, le=200)) -> List[Dict[str, Any]]:
    require_authenticated_identity(request, detail="Bad-actor reports require an authenticated identity")
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


@router.get("/prioritized-assets")
def prioritized_assets(
    request: Request,
    limit: int = Query(20, ge=1, le=200),
    window: int = Query(30, ge=1, le=365),
) -> List[Dict[str, Any]]:
    require_authenticated_identity(request, detail="Prioritized asset reports require an authenticated identity")
    s = Settings()
    conn = with_pg(s.pg_dsn)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(f"""
                SELECT asset_id, COUNT(*) AS ev_count, MAX(occurred_at) AS last_evt_at
                FROM events
                WHERE occurred_at > {_window_clause(window)}
                  AND asset_id IS NOT NULL
                GROUP BY asset_id
            """)
            event_rows = cur.fetchall()
            events = {
                str(row[0]): {"event_count": int(row[1] or 0), "last_event_at": row[2]}
                for row in event_rows or []
                if row and row[0]
            }

            cur.execute(f"""
                SELECT DISTINCT ON (asset_id) asset_id, severity, occurred_at
                FROM events
                WHERE occurred_at > {_window_clause(window)}
                  AND asset_id IS NOT NULL
                ORDER BY asset_id, occurred_at DESC
            """)
            severities = {
                str(row[0]): row[1]
                for row in cur.fetchall() or []
                if row and row[0]
            }

            cur.execute(f"""
                SELECT asset_id,
                       COUNT(*) AS wo_count,
                       SUM(CASE WHEN UPPER(COALESCE(status, '')) IN ('COMP', 'COMPLETE', 'COMPLETED', 'CLOSE', 'CLOSED', 'DONE') THEN 0 ELSE 1 END) AS open_wo_count
                FROM workorders
                WHERE COALESCE(workorder_created_at, handoff_completed_at, workorder_completed_at, NOW()) > {_window_clause(window)}
                  AND asset_id IS NOT NULL
                GROUP BY asset_id
            """)
            workorders = {
                str(row[0]): {
                    "workorder_count": int(row[1] or 0),
                    "open_workorder_count": int(row[2] or 0),
                }
                for row in cur.fetchall() or []
                if row and row[0]
            }

            cur.execute(f"""
                SELECT asset_id,
                       SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accept_count,
                       SUM(CASE WHEN action = 'reject' THEN 1 ELSE 0 END) AS reject_count
                FROM rca_feedback
                WHERE created_at > {_window_clause(window)}
                  AND asset_id IS NOT NULL
                GROUP BY asset_id
            """)
            feedback = _feedback_summary(cur.fetchall())

            cur.execute("""
                SELECT asset_id, period, anomaly_flags
                FROM signal_rollups
                WHERE end_time > NOW() - INTERVAL '24 hours'
                  AND asset_id IS NOT NULL
            """)
            signal_scores = _signal_anomaly_scores(cur.fetchall())

            cur.execute(f"""
                SELECT asset_id, occurred_at
                FROM events
                WHERE occurred_at > {_window_clause(window)}
                  AND asset_id IS NOT NULL
                ORDER BY asset_id, occurred_at
            """)
            mtbf_by_asset = _asset_mtbf(cur.fetchall())

        rows = []
        asset_ids = set(events) | set(workorders) | set(feedback) | set(signal_scores) | set(mtbf_by_asset)
        for asset_id in asset_ids:
            event_count = int(events.get(asset_id, {}).get("event_count", 0))
            workorder_count = int(workorders.get(asset_id, {}).get("workorder_count", 0))
            open_workorder_count = int(workorders.get(asset_id, {}).get("open_workorder_count", 0))
            signal_anomaly_score = float(signal_scores.get(asset_id, 0.0))
            acceptance_rate = feedback.get(asset_id, {}).get("acceptance_rate")
            mtbf_seconds = mtbf_by_asset.get(asset_id)
            score_components = _score_asset(
                latest_severity=severities.get(asset_id),
                event_count=event_count,
                workorder_count=workorder_count,
                open_workorder_count=open_workorder_count,
                signal_anomaly_score=signal_anomaly_score,
                acceptance_rate=acceptance_rate,
                mtbf_seconds=mtbf_seconds,
            )
            rows.append(
                {
                    "asset_id": asset_id,
                    "priority_score": score_components["priority_score"],
                    "latest_severity": severities.get(asset_id),
                    "last_event_at": _to_isoformat(events.get(asset_id, {}).get("last_event_at")),
                    "events_window": event_count,
                    "workorders_window": workorder_count,
                    "open_workorders": open_workorder_count,
                    "signal_anomaly_score": signal_anomaly_score,
                    "feedback_acceptance_rate": acceptance_rate,
                    "mtbf_seconds": mtbf_seconds,
                    "score_components": {
                        key: value
                        for key, value in score_components.items()
                        if key != "priority_score"
                    },
                }
            )
        rows.sort(key=lambda row: (-float(row["priority_score"]), row["asset_id"]))
        return rows[:limit]
    finally:
        try:
            conn.close()
        except Exception:
            pass
