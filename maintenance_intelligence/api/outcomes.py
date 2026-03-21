from fastapi import APIRouter, HTTPException, Query, Request, Response
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
import io
import csv
import psycopg2
from maintenance_intelligence.api.middleware.identity import require_authenticated_identity
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services.pdm_scorer import (
    build_early_warning_report,
    empty_early_warning_summary,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
FEEDBACK_ACTIONS = ("accept", "reject", "edited")
CMMS_SUMMARY_FIELDS = (
    "success_total",
    "pending_total",
    "failure_total",
    "admin_retry_required_total",
    "limit_reached_total",
    "approval_to_handoff_seconds_avg",
)
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


def _empty_cmms_summary() -> Dict[str, Any]:
    return {
        "success_total": 0,
        "pending_total": 0,
        "failure_total": 0,
        "admin_retry_required_total": 0,
        "limit_reached_total": 0,
        "approval_to_handoff_seconds_avg": None,
    }


def _base_outcomes(window: int) -> Dict[str, Any]:
    return {
        "window_days": int(window),
        "status": "ok",
        "warnings": [],
        "early_warning_summary": empty_early_warning_summary(),
        "feedback_counts": {action: 0 for action in FEEDBACK_ACTIONS},
        "feedback_total": 0,
        "acceptance_rate": None,
        "ttr_seconds_avg": None,
        "mtbf_seconds_avg": None,
        "mttr_seconds_avg": None,
        "top_assets_by_wo_volume": [],
        "top_backends_by_handoff_volume": [],
        "top_users_by_feedback": [],
        "top_orgs_by_feedback": [],
        "cmms_summary": _empty_cmms_summary(),
        "cmms_breakdowns": {
            "by_asset": {},
            "by_backend": {},
        },
        "asset_metrics": {},
        "backend_metrics": {},
        "user_metrics": {},
        "org_metrics": {},
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
    _set_group_metric_series(out, "asset_metrics", metric_name, series, bucket_dates)


def _set_group_metric_series(
    out: Dict[str, Any],
    group_key: str,
    metric_name: str,
    series: Dict[str, List[Dict[str, Any]]],
    bucket_dates: List[str],
) -> None:
    group_metrics = out.setdefault(group_key, {})
    group_ids = set(group_metrics) | set(series)
    for group_id in sorted(group_ids):
        group_entry = group_metrics.setdefault(group_id, {})
        empty_value = 0 if metric_name == "workorder_volume" else None
        if metric_name == "feedback_volume":
            empty_value = 0
        group_entry[metric_name] = series.get(
            group_id, _empty_asset_series(bucket_dates, empty_value=empty_value)
        )


def _update_group_feedback_totals(out: Dict[str, Any], group_key: str, rows: List[Any]) -> None:
    group_metrics = out.setdefault(group_key, {})
    for row in rows or []:
        if not row or not row[0] or not row[1]:
            continue
        entity_id = str(row[0])
        action = str(row[1])
        count = int(row[2] or 0)
        entity_entry = group_metrics.setdefault(entity_id, {})
        counts = entity_entry.setdefault(
            "feedback_counts", {feedback_action: 0 for feedback_action in FEEDBACK_ACTIONS}
        )
        if action in FEEDBACK_ACTIONS:
            counts[action] = count
        total = sum(int(counts.get(feedback_action, 0)) for feedback_action in FEEDBACK_ACTIONS)
        entity_entry["feedback_total"] = total
        decided_total = int(counts.get("accept", 0)) + int(counts.get("reject", 0))
        entity_entry["acceptance_rate"] = (
            (int(counts.get("accept", 0)) / decided_total) if decided_total > 0 else None
        )


def _set_top_group_rows(out: Dict[str, Any], top_key: str, id_label: str, rows: List[Any]) -> None:
    out[top_key] = [
        {id_label: str(row[0]), "count": int(row[1] or 0)} for row in (rows or []) if row and row[0]
    ]


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _parse_timestamp_text(value: Any) -> datetime | None:
    text = _as_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _ensure_cmms_bucket(bucket: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in _empty_cmms_summary().items():
        bucket.setdefault(key, value)
    bucket.setdefault("_lead_time_total", 0.0)
    bucket.setdefault("_lead_time_count", 0)
    return bucket


def _proposal_asset_id(proposal_asset_id: Any, workorder_asset_id: Any) -> str:
    return _as_text(proposal_asset_id) or _as_text(workorder_asset_id) or "unknown"


def _workorder_backend(workorder_metadata: Any) -> str:
    metadata = workorder_metadata if isinstance(workorder_metadata, dict) else {}
    handoff = metadata.get("handoff") if isinstance(metadata.get("handoff"), dict) else {}
    backend = (_as_text(handoff.get("backend")) or "").lower()
    if backend:
        return backend
    source = (_as_text(metadata.get("source")) or "").lower()
    prefix = "agent-wo-bridge-"
    if source.startswith(prefix):
        derived_backend = source[len(prefix) :].strip()
        if derived_backend:
            return derived_backend
    return "unknown"


def _proposal_attempt_count(metadata: Any) -> int:
    if not isinstance(metadata, dict):
        return 0
    attempts = metadata.get("approval_attempts")
    if isinstance(attempts, list):
        return sum(1 for item in attempts if isinstance(item, dict))
    approval = metadata.get("approval")
    if isinstance(approval, dict) and any(
        _as_text(approval.get(field)) for field in ("attempted_at", "approved_at", "approved_by")
    ):
        return 1
    return 0


def _proposal_handoff_state(status: Any, work_order_id: Any, metadata: Any) -> str:
    approval = (
        metadata.get("approval")
        if isinstance(metadata, dict) and isinstance(metadata.get("approval"), dict)
        else {}
    )
    handoff_state = (_as_text(approval.get("handoff_state")) or "").lower()
    if handoff_state in {"success", "pending", "failure"}:
        return handoff_state
    if _as_text(status) == "approved" and _as_text(work_order_id):
        return "success"
    return "pending"


def _bucket_date_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "date") and hasattr(value, "isoformat"):
        date_value = value.date() if callable(getattr(value, "date", None)) else value
        return date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _as_text(value)


def _update_cmms_bucket(
    bucket: Dict[str, Any],
    status: Any,
    work_order_id: Any,
    proposal_metadata: Any,
    handoff_completed_at: Any,
    max_attempts: int,
) -> None:
    summary = _ensure_cmms_bucket(bucket)
    metadata = proposal_metadata if isinstance(proposal_metadata, dict) else {}
    attempt_count = _proposal_attempt_count(metadata)
    handoff_state = _proposal_handoff_state(status, work_order_id, metadata)

    if handoff_state == "success":
        summary["success_total"] = int(summary.get("success_total") or 0) + 1
    elif handoff_state == "failure":
        summary["failure_total"] = int(summary.get("failure_total") or 0) + 1
    else:
        summary["pending_total"] = int(summary.get("pending_total") or 0) + 1

    if _as_text(status) != "approved" and attempt_count > 0:
        summary["admin_retry_required_total"] = (
            int(summary.get("admin_retry_required_total") or 0) + 1
        )
    if _as_text(status) != "approved" and attempt_count >= max_attempts:
        summary["limit_reached_total"] = int(summary.get("limit_reached_total") or 0) + 1

    approval = metadata.get("approval") if isinstance(metadata.get("approval"), dict) else {}
    approved_at = _parse_timestamp_text(approval.get("approved_at") or approval.get("attempted_at"))
    if approved_at and handoff_completed_at:
        delta = (handoff_completed_at - approved_at).total_seconds()
        if delta >= 0:
            summary["_lead_time_total"] = float(summary.get("_lead_time_total") or 0.0) + delta
            summary["_lead_time_count"] = int(summary.get("_lead_time_count") or 0) + 1


def _finalize_cmms_bucket(bucket: Dict[str, Any]) -> None:
    summary = _ensure_cmms_bucket(bucket)
    lead_time_total = float(summary.pop("_lead_time_total", 0.0) or 0.0)
    lead_time_count = int(summary.pop("_lead_time_count", 0) or 0)
    summary["approval_to_handoff_seconds_avg"] = (
        (lead_time_total / lead_time_count) if lead_time_count > 0 else None
    )


def _update_cmms_summary(out: Dict[str, Any], rows: List[Any], max_attempts: int) -> None:
    summary = _ensure_cmms_bucket(out.setdefault("cmms_summary", _empty_cmms_summary()))
    breakdowns = out.setdefault("cmms_breakdowns", {"by_asset": {}, "by_backend": {}})
    by_asset = breakdowns.setdefault("by_asset", {})
    by_backend = breakdowns.setdefault("by_backend", {})

    for row in rows or []:
        if not row:
            continue
        status = row[1]
        work_order_id = row[2]
        proposal_metadata = row[3] if isinstance(row[3], dict) else {}
        handoff_completed_at = row[4] if len(row) > 4 else None
        proposal_asset_id = row[5] if len(row) > 5 else None
        workorder_asset_id = row[6] if len(row) > 6 else None
        workorder_metadata = row[7] if len(row) > 7 and isinstance(row[7], dict) else {}

        _update_cmms_bucket(
            summary, status, work_order_id, proposal_metadata, handoff_completed_at, max_attempts
        )

        asset_key = _proposal_asset_id(proposal_asset_id, workorder_asset_id)
        backend_key = _workorder_backend(workorder_metadata)
        _update_cmms_bucket(
            by_asset.setdefault(asset_key, _empty_cmms_summary()),
            status,
            work_order_id,
            proposal_metadata,
            handoff_completed_at,
            max_attempts,
        )
        _update_cmms_bucket(
            by_backend.setdefault(backend_key, _empty_cmms_summary()),
            status,
            work_order_id,
            proposal_metadata,
            handoff_completed_at,
            max_attempts,
        )

    _finalize_cmms_bucket(summary)
    for bucket in by_asset.values():
        _finalize_cmms_bucket(bucket)
    for bucket in by_backend.values():
        _finalize_cmms_bucket(bucket)


def _update_backend_metrics(out: Dict[str, Any], rows: List[Any], bucket_dates: List[str]) -> None:
    backend_metrics = out.setdefault("backend_metrics", {})
    handoff_volume: Dict[str, Dict[str, int]] = {}
    success_counts: Dict[str, int] = {}
    terminal_counts: Dict[str, int] = {}
    daily_success_counts: Dict[str, Dict[str, int]] = {}
    daily_terminal_counts: Dict[str, Dict[str, int]] = {}
    total_counts: Dict[str, int] = {}

    for row in rows or []:
        if not row:
            continue
        status = row[1]
        work_order_id = row[2]
        proposal_metadata = row[3] if isinstance(row[3], dict) else {}
        workorder_metadata = row[7] if len(row) > 7 and isinstance(row[7], dict) else {}
        created_at = row[8] if len(row) > 8 else None
        backend_key = _workorder_backend(workorder_metadata)
        handoff_state = _proposal_handoff_state(status, work_order_id, proposal_metadata)
        backend_entry = backend_metrics.setdefault(backend_key, {})
        backend_entry["handoff_total"] = int(backend_entry.get("handoff_total") or 0) + 1
        total_counts[backend_key] = int(total_counts.get(backend_key) or 0) + 1

        if handoff_state in {"success", "failure"}:
            terminal_counts[backend_key] = int(terminal_counts.get(backend_key) or 0) + 1
            if handoff_state == "success":
                success_counts[backend_key] = int(success_counts.get(backend_key) or 0) + 1

        bucket_date = _bucket_date_text(created_at)
        if bucket_date:
            handoff_volume.setdefault(backend_key, {})[bucket_date] = (
                int(handoff_volume.setdefault(backend_key, {}).get(bucket_date) or 0) + 1
            )
            if handoff_state in {"success", "failure"}:
                daily_terminal_counts.setdefault(backend_key, {})[bucket_date] = (
                    int(daily_terminal_counts.setdefault(backend_key, {}).get(bucket_date) or 0) + 1
                )
                if handoff_state == "success":
                    daily_success_counts.setdefault(backend_key, {})[bucket_date] = (
                        int(daily_success_counts.setdefault(backend_key, {}).get(bucket_date) or 0)
                        + 1
                    )

    success_rate_series: Dict[str, Dict[str, float | None]] = {}
    for backend_key, per_day in daily_terminal_counts.items():
        for bucket_date, total in per_day.items():
            success_total = int((daily_success_counts.get(backend_key) or {}).get(bucket_date) or 0)
            success_rate_series.setdefault(backend_key, {})[bucket_date] = (
                (success_total / total) if total > 0 else None
            )

    for backend_key in set(backend_metrics) | set(total_counts) | set(terminal_counts):
        backend_entry = backend_metrics.setdefault(backend_key, {})
        backend_entry["handoff_total"] = int(
            total_counts.get(backend_key) or backend_entry.get("handoff_total") or 0
        )
        terminal_total = int(terminal_counts.get(backend_key) or 0)
        backend_entry["handoff_success_rate"] = (
            (int(success_counts.get(backend_key) or 0) / terminal_total)
            if terminal_total > 0
            else None
        )

    out["top_backends_by_handoff_volume"] = [
        {"backend": backend_key, "count": count}
        for backend_key, count in sorted(
            total_counts.items(), key=lambda item: (-item[1], item[0])
        )[:10]
    ]
    _set_group_metric_series(
        out,
        "backend_metrics",
        "handoff_volume",
        _series_to_rows(handoff_volume, bucket_dates, empty_value=0),
        bucket_dates,
    )
    _set_group_metric_series(
        out,
        "backend_metrics",
        "handoff_success_rate_series",
        _series_to_rows(success_rate_series, bucket_dates, empty_value=None),
        bucket_dates,
    )


@router.get("/rca-outcomes")
def rca_outcomes(request: Request, window: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    require_authenticated_identity(
        request, detail="Outcomes reports require an authenticated identity"
    )
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

            try:
                cur.execute(f"""
                    SELECT asset_id, severity, occurred_at, details
                    FROM events
                    WHERE occurred_at > {_window_clause(window)}
                      AND asset_id IS NOT NULL
                      AND kind IN ('alarm', 'anomaly', 'measurement')
                    ORDER BY asset_id, occurred_at DESC
                """)
                early_warning_event_rows = cur.fetchall()

                cur.execute(f"""
                    SELECT asset_id,
                           signal_type,
                           period,
                           end_time,
                           mean_value,
                           max_value,
                           anomaly_flags
                    FROM signal_rollups
                    WHERE end_time > {_window_clause(window)}
                      AND asset_id IS NOT NULL
                      AND period IN ('1h', '6h', '24h')
                    ORDER BY asset_id, end_time DESC
                """)
                early_warning_rollup_rows = cur.fetchall()
                early_warning = build_early_warning_report(
                    early_warning_event_rows, early_warning_rollup_rows
                )
                out["early_warning_summary"] = early_warning["summary"]
                for asset_id, asset_warning in (early_warning.get("asset_metrics") or {}).items():
                    out.setdefault("asset_metrics", {}).setdefault(asset_id, {}).update(
                        asset_warning
                    )
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"early warning summary unavailable: {exc}")

            try:
                max_attempts = max(1, int(s.pm_handoff_max_attempts_per_proposal))
                cur.execute(f"""
                    SELECT p.proposal_id,
                           p.status,
                           p.work_order_id,
                           p.metadata,
                           w.handoff_completed_at,
                           p.asset_id,
                           w.asset_id,
                           w.metadata,
                           p.created_at
                    FROM pm_proposals p
                    LEFT JOIN workorders w ON w.wo_id = p.work_order_id
                    WHERE p.created_at > {_window_clause(window)}
                """)
                cmms_rows = cur.fetchall()
                _update_cmms_summary(out, cmms_rows, max_attempts)
                _update_backend_metrics(out, cmms_rows, bucket_dates)
            except Exception as exc:
                _safe_rollback(conn)
                _mark_partial(out, f"cmms handoff summary unavailable: {exc}")

            for entity_field, group_key, top_key, id_label, warning_prefix in (
                ("user_id", "user_metrics", "top_users_by_feedback", "user_id", "user analytics"),
                ("org_id", "org_metrics", "top_orgs_by_feedback", "org_id", "org analytics"),
            ):
                try:
                    cur.execute(f"""
                        SELECT {entity_field} AS entity_id, action, COUNT(*) AS n
                        FROM rca_feedback
                        WHERE created_at > {_window_clause(window)}
                          AND {entity_field} IS NOT NULL
                        GROUP BY entity_id, action
                        ORDER BY entity_id, action
                    """)
                    _update_group_feedback_totals(out, group_key, cur.fetchall())
                except Exception as exc:
                    _safe_rollback(conn)
                    _mark_partial(out, f"{warning_prefix} feedback totals unavailable: {exc}")

                try:
                    cur.execute(f"""
                        SELECT {entity_field} AS entity_id,
                               DATE_TRUNC('day', created_at)::date AS bucket_date,
                               COUNT(*) AS n
                        FROM rca_feedback
                        WHERE created_at > {_window_clause(window)}
                          AND {entity_field} IS NOT NULL
                        GROUP BY entity_id, bucket_date
                        ORDER BY entity_id, bucket_date
                    """)
                    feedback_volume: Dict[str, Dict[str, int]] = {}
                    for row in cur.fetchall() or []:
                        if not row or not row[0] or not row[1]:
                            continue
                        entity_id = str(row[0])
                        bucket_date = (
                            row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])
                        )
                        feedback_volume.setdefault(entity_id, {})[bucket_date] = int(row[2] or 0)
                    _set_group_metric_series(
                        out,
                        group_key,
                        "feedback_volume",
                        _series_to_rows(feedback_volume, bucket_dates, empty_value=0),
                        bucket_dates,
                    )
                except Exception as exc:
                    _safe_rollback(conn)
                    _mark_partial(out, f"{warning_prefix} feedback trend unavailable: {exc}")

                try:
                    cur.execute(f"""
                        SELECT {entity_field} AS entity_id,
                               DATE_TRUNC('day', created_at)::date AS bucket_date,
                               SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accepted_count,
                               SUM(CASE WHEN action = 'reject' THEN 1 ELSE 0 END) AS rejected_count
                        FROM rca_feedback
                        WHERE created_at > {_window_clause(window)}
                          AND action IN ('accept', 'reject')
                          AND {entity_field} IS NOT NULL
                        GROUP BY entity_id, bucket_date
                        ORDER BY entity_id, bucket_date
                    """)
                    acceptance_rate: Dict[str, Dict[str, float | None]] = {}
                    for row in cur.fetchall() or []:
                        if not row or not row[0] or not row[1]:
                            continue
                        entity_id = str(row[0])
                        bucket_date = (
                            row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])
                        )
                        accepted_count = int(row[2] or 0)
                        rejected_count = int(row[3] or 0)
                        total = accepted_count + rejected_count
                        acceptance_rate.setdefault(entity_id, {})[bucket_date] = (
                            (accepted_count / total) if total > 0 else None
                        )
                    _set_group_metric_series(
                        out,
                        group_key,
                        "acceptance_rate_series",
                        _series_to_rows(acceptance_rate, bucket_dates, empty_value=None),
                        bucket_dates,
                    )
                except Exception as exc:
                    _safe_rollback(conn)
                    _mark_partial(out, f"{warning_prefix} acceptance trend unavailable: {exc}")

                try:
                    cur.execute(f"""
                        SELECT {entity_field} AS entity_id, COUNT(*) AS n
                        FROM rca_feedback
                        WHERE created_at > {_window_clause(window)}
                          AND {entity_field} IS NOT NULL
                        GROUP BY entity_id
                        ORDER BY n DESC, entity_id ASC
                        LIMIT 10
                    """)
                    _set_top_group_rows(out, top_key, id_label, cur.fetchall())
                except Exception as exc:
                    _safe_rollback(conn)
                    _mark_partial(out, f"{warning_prefix} leaderboard unavailable: {exc}")

        return out
    finally:
        conn.close()


@router.get("/rca-outcomes/csv")
def rca_outcomes_csv(request: Request, window: int = Query(30, ge=1, le=365)):
    # Flatten a report view for leadership export
    rep = rca_outcomes(request=request, window=window)  # reuse computation
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
    early_warning_summary = rep.get("early_warning_summary") or {}
    rows.append(
        {
            "metric": "early_warning_total_assets",
            "value": early_warning_summary.get("total_assets", 0),
        }
    )
    for status_name, status_total in (early_warning_summary.get("status_counts") or {}).items():
        rows.append({"metric": f"early_warning_{status_name}_total", "value": status_total})
    rows.append(
        {
            "metric": "early_warning_last_evaluated_at",
            "value": early_warning_summary.get("last_evaluated_at"),
        }
    )
    for top_asset in early_warning_summary.get("top_assets") or []:
        asset_id = top_asset.get("asset_id")
        if not asset_id:
            continue
        rows.append(
            {"metric": f"early_warning_top_asset_{asset_id}_score", "value": top_asset.get("score")}
        )
        rows.append(
            {
                "metric": f"early_warning_top_asset_{asset_id}_status",
                "value": top_asset.get("status"),
            }
        )
    cmms_summary = rep.get("cmms_summary") or {}
    rows.append({"metric": "cmms_success_total", "value": cmms_summary.get("success_total", 0)})
    rows.append({"metric": "cmms_pending_total", "value": cmms_summary.get("pending_total", 0)})
    rows.append({"metric": "cmms_failure_total", "value": cmms_summary.get("failure_total", 0)})
    rows.append(
        {
            "metric": "cmms_admin_retry_required_total",
            "value": cmms_summary.get("admin_retry_required_total", 0),
        }
    )
    rows.append(
        {"metric": "cmms_limit_reached_total", "value": cmms_summary.get("limit_reached_total", 0)}
    )
    rows.append(
        {
            "metric": "cmms_approval_to_handoff_seconds_avg",
            "value": cmms_summary.get("approval_to_handoff_seconds_avg"),
        }
    )
    cmms_breakdowns = rep.get("cmms_breakdowns") or {}
    for asset_id, asset_summary in (cmms_breakdowns.get("by_asset") or {}).items():
        for metric_name in CMMS_SUMMARY_FIELDS:
            rows.append(
                {
                    "metric": f"cmms_asset_{asset_id}_{metric_name}",
                    "value": asset_summary.get(metric_name),
                }
            )
    for backend, backend_summary in (cmms_breakdowns.get("by_backend") or {}).items():
        for metric_name in CMMS_SUMMARY_FIELDS:
            rows.append(
                {
                    "metric": f"cmms_backend_{backend}_{metric_name}",
                    "value": backend_summary.get(metric_name),
                }
            )
    # Asset highlights as separate rows for easier slicing
    for a in rep.get("top_assets_by_wo_volume") or []:
        rows.append({"metric": f"top_asset_{a['asset_id']}_wo_count", "value": a["count"]})
    for backend_row in rep.get("top_backends_by_handoff_volume") or []:
        rows.append(
            {
                "metric": f"top_backend_{backend_row['backend']}_handoff_count",
                "value": backend_row["count"],
            }
        )
    for asset_id, asset_metrics in (rep.get("asset_metrics") or {}).items():
        rows.append(
            {
                "metric": f"asset_{asset_id}_early_warning_score",
                "value": asset_metrics.get("early_warning_score"),
            }
        )
        rows.append(
            {
                "metric": f"asset_{asset_id}_early_warning_status",
                "value": asset_metrics.get("early_warning_status"),
            }
        )
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
    for backend, backend_metrics in (rep.get("backend_metrics") or {}).items():
        rows.append(
            {
                "metric": f"backend_{backend}_handoff_total",
                "value": backend_metrics.get("handoff_total"),
            }
        )
        rows.append(
            {
                "metric": f"backend_{backend}_handoff_success_rate",
                "value": backend_metrics.get("handoff_success_rate"),
            }
        )
        for point in backend_metrics.get("handoff_volume") or []:
            rows.append(
                {
                    "metric": f"backend_{backend}_handoff_volume_{point['date']}",
                    "value": point.get("value", 0),
                }
            )
        for point in backend_metrics.get("handoff_success_rate_series") or []:
            rows.append(
                {
                    "metric": f"backend_{backend}_handoff_success_rate_{point['date']}",
                    "value": point.get("value"),
                }
            )
    for entity_name, metrics_key in (("user", "user_metrics"), ("org", "org_metrics")):
        for entity_id, entity_metrics in (rep.get(metrics_key) or {}).items():
            feedback_counts = entity_metrics.get("feedback_counts") or {}
            for action in FEEDBACK_ACTIONS:
                rows.append(
                    {
                        "metric": f"{entity_name}_{entity_id}_feedback_{action}",
                        "value": feedback_counts.get(action, 0),
                    }
                )
            rows.append(
                {
                    "metric": f"{entity_name}_{entity_id}_feedback_total",
                    "value": entity_metrics.get("feedback_total"),
                }
            )
            rows.append(
                {
                    "metric": f"{entity_name}_{entity_id}_acceptance_rate",
                    "value": entity_metrics.get("acceptance_rate"),
                }
            )
            for point in entity_metrics.get("feedback_volume") or []:
                rows.append(
                    {
                        "metric": f"{entity_name}_{entity_id}_feedback_volume_{point['date']}",
                        "value": point.get("value", 0),
                    }
                )
            for point in entity_metrics.get("acceptance_rate_series") or []:
                rows.append(
                    {
                        "metric": f"{entity_name}_{entity_id}_acceptance_rate_{point['date']}",
                        "value": point.get("value"),
                    }
                )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["metric", "value"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv")
