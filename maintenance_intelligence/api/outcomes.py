from fastapi import APIRouter, HTTPException, Query, Response
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
import io
import csv
import psycopg2
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
FEEDBACK_ACTIONS = ("accept", "reject", "edited")
PLACEHOLDER_NOTES = {
    "mtbf_seconds_avg": "Placeholder until work order lifecycle/failure intervals are available.",
    "mttr_seconds_avg": "Placeholder until work order lifecycle repair timestamps are available.",
}


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


def _base_outcomes(window: int) -> Dict[str, Any]:
    return {
        "window_days": int(window),
        "status": "ok",
        "warnings": [],
        "feedback_counts": {action: 0 for action in FEEDBACK_ACTIONS},
        "feedback_total": 0,
        "acceptance_rate": None,
        "ttr_seconds_avg": None,
        "mtbf_seconds_avg": None,
        "mttr_seconds_avg": None,
        "top_assets_by_wo_volume": [],
        "asset_metrics": {},
        "placeholders": dict(PLACEHOLDER_NOTES),
    }


def _mark_partial(out: Dict[str, Any], message: str) -> None:
    out["status"] = "partial"
    out.setdefault("warnings", []).append(message)


def _clear_placeholder(out: Dict[str, Any], metric_name: str) -> None:
    placeholders = out.get("placeholders")
    if isinstance(placeholders, dict):
        placeholders.pop(metric_name, None)


def _safe_rollback(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def _bucket_dates(window: int, now: datetime | None = None) -> List[str]:
    anchor = now or datetime.now(timezone.utc)
    start = (anchor - timedelta(days=max(0, int(window) - 1))).date()
    return [(start + timedelta(days=offset)).isoformat() for offset in range(int(window))]


def _empty_asset_series(bucket_dates: List[str], *, empty_value: Any) -> List[Dict[str, Any]]:
    return [{"date": bucket_date, "value": empty_value} for bucket_date in bucket_dates]


def _series_to_rows(
    values: Dict[str, Dict[str, Any]], bucket_dates: List[str], *, empty_value: Any
) -> Dict[str, List[Dict[str, Any]]]:
    rows: Dict[str, List[Dict[str, Any]]] = {}
    for asset_id, per_day in values.items():
        rows[asset_id] = [
            {"date": bucket_date, "value": per_day.get(bucket_date, empty_value)}
            for bucket_date in bucket_dates
        ]
    return rows


def _set_asset_metric_series(
    out: Dict[str, Any],
    metric_name: str,
    series: Dict[str, List[Dict[str, Any]]],
    bucket_dates: List[str],
) -> None:
    asset_metrics = out.setdefault("asset_metrics", {})
    asset_ids = set(asset_metrics) | set(series)
    for asset_id in sorted(asset_ids):
        asset_entry = asset_metrics.setdefault(asset_id, {})
        empty_value = 0 if metric_name == "workorder_volume" else None
        asset_entry[metric_name] = series.get(
            asset_id, _empty_asset_series(bucket_dates, empty_value=empty_value)
        )


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
        out = _base_outcomes(window)
        bucket_dates = _bucket_dates(window)
        with conn.cursor() as cur:
            # Feedback counts by action (accept/reject/edited)
            try:
                cur.execute(f"""
                    SELECT action, COUNT(*) FROM rca_feedback
                    WHERE created_at > {_window_clause(window)}
                    GROUP BY action
                """)
                fb = {r[0]: int(r[1]) for r in cur.fetchall() if r and r[0]}
                out["feedback_counts"].update({key: fb.get(key, 0) for key in FEEDBACK_ACTIONS})
                out["feedback_total"] = sum(out["feedback_counts"].values())
                accept = out["feedback_counts"].get("accept", 0)
                out["acceptance_rate"] = (
                    (accept / out["feedback_total"]) if out["feedback_total"] > 0 else None
                )
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"feedback aggregation unavailable: {exc}")

            # Approx TTR: recommendation -> canonical workorder creation timestamp.
            try:
                cur.execute(f"""
                    SELECT w.wo_id, w.workorder_created_at AS wo_ts,
                           e.occurred_at AS rec_ts, w.asset_id
                    FROM workorders w
                    JOIN events e ON (
                        e.event_id = ANY(string_to_array(COALESCE(w.metadata->>'evidence_event_id', ''), ','))
                        OR (
                            COALESCE(w.metadata->>'evidence_event_id', '') = ''
                            AND e.asset_id = w.asset_id
                        )
                    )
                    WHERE COALESCE(w.workorder_created_at, w.handoff_completed_at, w.workorder_completed_at, NOW()) > {_window_clause(window)}
                    LIMIT 500
                """)
                ttrs = []
                for row in cur.fetchall() or []:
                    wo_ts, rec_ts = row[1], row[2]
                    if wo_ts and rec_ts:
                        delta = (wo_ts - rec_ts).total_seconds()
                        if delta >= 0:
                            ttrs.append(delta)
                out["ttr_seconds_avg"] = (sum(ttrs) / len(ttrs)) if ttrs else None
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"ttr aggregation unavailable: {exc}")

            # Proxy MTBF: mean interval between successive events for the same asset.
            # This uses event cadence as a precursor until explicit failure lifecycle data exists.
            try:
                cur.execute(f"""
                    SELECT asset_id, occurred_at
                    FROM events
                    WHERE occurred_at > {_window_clause(window)}
                      AND asset_id IS NOT NULL
                    ORDER BY asset_id, occurred_at
                """)
                last_seen: Dict[str, Any] = {}
                intervals: List[float] = []
                for row in cur.fetchall() or []:
                    if not row or not row[0] or not row[1]:
                        continue
                    asset_id = str(row[0])
                    event_ts = row[1]
                    previous_ts = last_seen.get(asset_id)
                    if previous_ts is not None:
                        delta = (event_ts - previous_ts).total_seconds()
                        if delta >= 0:
                            intervals.append(delta)
                    last_seen[asset_id] = event_ts
                out["mtbf_seconds_avg"] = (sum(intervals) / len(intervals)) if intervals else None
                if out["mtbf_seconds_avg"] is not None:
                    _clear_placeholder(out, "mtbf_seconds_avg")
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"mtbf aggregation unavailable: {exc}")

            # Proxy MTTR: terminal workorders with canonical lifecycle timestamps.
            try:
                cur.execute(f"""
                    SELECT w.wo_id,
                           w.workorder_created_at AS created_ts,
                           w.workorder_completed_at AS completed_ts,
                           w.status
                    FROM workorders w
                    WHERE COALESCE(w.workorder_created_at, w.handoff_completed_at, w.workorder_completed_at, NOW()) > {_window_clause(window)}
                      AND UPPER(COALESCE(w.status, '')) IN ('COMP', 'COMPLETE', 'COMPLETED', 'CLOSE', 'CLOSED', 'DONE')
                """)
                mttrs = []
                for row in cur.fetchall() or []:
                    if not row:
                        continue
                    created_ts = row[1]
                    completed_ts = row[2]
                    if created_ts and completed_ts:
                        delta = (completed_ts - created_ts).total_seconds()
                        if delta >= 0:
                            mttrs.append(delta)
                out["mttr_seconds_avg"] = (sum(mttrs) / len(mttrs)) if mttrs else None
                if out["mttr_seconds_avg"] is not None:
                    _clear_placeholder(out, "mttr_seconds_avg")
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"mttr aggregation unavailable: {exc}")

            # Per-asset summary (top 10 by slowest TTR)
            # This is a placeholder; improve with real WO lifecycle timestamps.
            try:
                cur.execute(f"""
                    SELECT w.asset_id, COUNT(*) AS n
                    FROM workorders w
                    WHERE COALESCE(w.workorder_created_at, w.handoff_completed_at, w.workorder_completed_at, NOW()) > {_window_clause(window)}
                    GROUP BY w.asset_id
                    ORDER BY n DESC
                    LIMIT 10
                """)
                out["top_assets_by_wo_volume"] = [
                    {"asset_id": r[0], "count": int(r[1])} for r in cur.fetchall() if r
                ]
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"asset volume aggregation unavailable: {exc}")

            try:
                cur.execute(f"""
                    SELECT w.asset_id,
                           DATE_TRUNC('day', COALESCE(w.workorder_created_at, w.handoff_completed_at, w.workorder_completed_at, NOW()))::date AS bucket_date,
                           COUNT(*) AS n
                    FROM workorders w
                    WHERE COALESCE(w.workorder_created_at, w.handoff_completed_at, w.workorder_completed_at, NOW()) > {_window_clause(window)}
                    GROUP BY w.asset_id, bucket_date
                    ORDER BY w.asset_id, bucket_date
                """)
                workorder_volume: Dict[str, Dict[str, int]] = {}
                for row in cur.fetchall() or []:
                    if not row or not row[0] or not row[1]:
                        continue
                    asset_id = str(row[0])
                    bucket_date = (
                        row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])
                    )
                    workorder_volume.setdefault(asset_id, {})[bucket_date] = int(row[2] or 0)
                _set_asset_metric_series(
                    out,
                    "workorder_volume",
                    _series_to_rows(workorder_volume, bucket_dates, empty_value=0),
                    bucket_dates,
                )
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"asset workorder trend unavailable: {exc}")

            try:
                cur.execute(f"""
                    SELECT asset_id,
                           DATE_TRUNC('day', created_at)::date AS bucket_date,
                           SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accepted_count,
                           SUM(CASE WHEN action = 'reject' THEN 1 ELSE 0 END) AS rejected_count
                    FROM rca_feedback
                    WHERE created_at > {_window_clause(window)}
                      AND action IN ('accept', 'reject')
                      AND asset_id IS NOT NULL
                    GROUP BY asset_id, bucket_date
                    ORDER BY asset_id, bucket_date
                """)
                acceptance_rate: Dict[str, Dict[str, float | None]] = {}
                for row in cur.fetchall() or []:
                    if not row or not row[0] or not row[1]:
                        continue
                    asset_id = str(row[0])
                    bucket_date = (
                        row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])
                    )
                    accepted_count = int(row[2] or 0)
                    rejected_count = int(row[3] or 0)
                    total = accepted_count + rejected_count
                    acceptance_rate.setdefault(asset_id, {})[bucket_date] = (
                        (accepted_count / total) if total > 0 else None
                    )
                _set_asset_metric_series(
                    out,
                    "acceptance_rate",
                    _series_to_rows(acceptance_rate, bucket_dates, empty_value=None),
                    bucket_dates,
                )
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"asset acceptance trend unavailable: {exc}")

        return out
    finally:
        conn.close()


@router.get("/rca-outcomes/csv")
def rca_outcomes_csv(window: int = Query(30, ge=1, le=365)):
    # Flatten a report view for leadership export
    rep = rca_outcomes(window=window)  # reuse computation
    rows = []
    # Feedback counts by action -> key/value rows
    for k in FEEDBACK_ACTIONS:
        v = (rep.get("feedback_counts") or {}).get(k, 0)
        rows.append({"metric": f"feedback_{k}", "value": v})
    rows.append({"metric": "feedback_total", "value": rep.get("feedback_total")})
    rows.append({"metric": "report_status", "value": rep.get("status")})
    rows.append({"metric": "warning_count", "value": len(rep.get("warnings") or [])})
    rows.append({"metric": "acceptance_rate", "value": rep.get("acceptance_rate")})
    rows.append({"metric": "ttr_seconds_avg", "value": rep.get("ttr_seconds_avg")})
    rows.append({"metric": "mtbf_seconds_avg", "value": rep.get("mtbf_seconds_avg")})
    rows.append({"metric": "mttr_seconds_avg", "value": rep.get("mttr_seconds_avg")})
    # Asset highlights as separate rows for easier slicing
    for a in rep.get("top_assets_by_wo_volume") or []:
        rows.append({"metric": f"top_asset_{a['asset_id']}_wo_count", "value": a["count"]})
    for asset_id, asset_metrics in (rep.get("asset_metrics") or {}).items():
        for point in asset_metrics.get("workorder_volume") or []:
            rows.append(
                {
                    "metric": f"asset_{asset_id}_workorder_volume_{point['date']}",
                    "value": point.get("value", 0),
                }
            )
        for point in asset_metrics.get("acceptance_rate") or []:
            rows.append(
                {
                    "metric": f"asset_{asset_id}_acceptance_rate_{point['date']}",
                    "value": point.get("value"),
                }
            )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["metric", "value"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv")
