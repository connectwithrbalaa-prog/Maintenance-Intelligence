import csv
import datetime as dt
import io
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
import psycopg2
from maintenance_intelligence.api.auth import require_role
from maintenance_intelligence.multitenancy import TenantContext, org_scope_enabled
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


def _org_scope_sql(settings: Settings, org_id: str, column: str = "org_id") -> tuple[str, tuple[Any, ...]]:
    if not org_scope_enabled(settings):
        return "", ()
    return f" AND {column} = %s", (org_id,)


def _parse_timestamp(value: Any) -> Optional[dt.datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        return dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _resolution_timestamp(metadata: Any) -> Optional[dt.datetime]:
    metadata = metadata if isinstance(metadata, dict) else {}
    return _parse_timestamp(metadata.get("resolved_at")) or _parse_timestamp(metadata.get("created_at"))


def _evidence_event_id(metadata: Any) -> Optional[str]:
    metadata = metadata if isinstance(metadata, dict) else {}
    value = metadata.get("evidence_event_id")
    if not isinstance(value, str):
        return None
    for candidate in value.split(","):
        cleaned = candidate.strip()
        if cleaned:
            return cleaned
    return None


def _find_ttr_event(
    workorder: Dict[str, Any],
    exact_events: Dict[str, Dict[str, Any]],
    asset_events: Dict[str, List[Dict[str, Any]]],
    fallback_window_h: int,
) -> Optional[Dict[str, Any]]:
    evidence_event_id = _evidence_event_id(workorder.get("metadata"))
    if evidence_event_id:
        return exact_events.get(evidence_event_id)

    wo_ts = workorder.get("wo_ts")
    asset_id = workorder.get("asset_id")
    if not wo_ts or not asset_id:
        return None

    best_event: Optional[Dict[str, Any]] = None
    best_delta: Optional[dt.timedelta] = None
    max_delta = dt.timedelta(hours=fallback_window_h)
    for event in asset_events.get(asset_id, []):
        occurred_at = event.get("occurred_at")
        if not occurred_at:
            continue
        delta = abs(wo_ts - occurred_at)
        if delta > max_delta:
            continue
        if best_delta is None or delta < best_delta:
            best_event = event
            best_delta = delta
    return best_event


def _build_ttr_measurements(
    workorders: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    fallback_window_h: int,
) -> List[Dict[str, Any]]:
    exact_events = {event["event_id"]: event for event in events if event.get("event_id")}
    asset_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        asset_id = event.get("asset_id")
        if asset_id:
            asset_events[asset_id].append(event)

    measurements: List[Dict[str, Any]] = []
    for workorder in workorders:
        wo_ts = _resolution_timestamp(workorder.get("metadata"))
        if not wo_ts:
            continue

        match = _find_ttr_event(
            {**workorder, "wo_ts": wo_ts},
            exact_events=exact_events,
            asset_events=asset_events,
            fallback_window_h=fallback_window_h,
        )
        if not match or not match.get("occurred_at"):
            continue

        delta_s = (wo_ts - match["occurred_at"]).total_seconds()
        if delta_s < 0:
            continue

        measurements.append(
            {
                "wo_id": workorder.get("wo_id"),
                "asset_id": workorder.get("asset_id"),
                "event_id": match.get("event_id"),
                "ttr_seconds": delta_s,
            }
        )
    return measurements


def _fetch_workorders_for_ttr(cur, window: int, settings: Settings, org_id: str) -> List[Dict[str, Any]]:
    org_sql, org_params = _org_scope_sql(settings, org_id)
    cur.execute(
        f"""
            SELECT wo_id, asset_id, metadata
            FROM workorders
            WHERE COALESCE((metadata->>'created_at')::timestamptz, NOW()) > {_window_clause(window)}{org_sql}
            ORDER BY COALESCE((metadata->>'created_at')::timestamptz, NOW()) DESC
            LIMIT 500
        """,
        org_params,
    )
    return [
        {"wo_id": row[0], "asset_id": row[1], "metadata": row[2] or {}}
        for row in (cur.fetchall() or [])
    ]


def _fetch_candidate_events(
    cur,
    workorders: List[Dict[str, Any]],
    fallback_window_h: int,
    settings: Settings,
    org_id: str,
) -> List[Dict[str, Any]]:
    evidence_event_ids = []
    asset_ids = set()
    workorder_timestamps = []

    for workorder in workorders:
        metadata = workorder.get("metadata") or {}
        evidence_event_id = _evidence_event_id(metadata)
        if evidence_event_id:
            evidence_event_ids.append(evidence_event_id)
        asset_id = workorder.get("asset_id")
        if asset_id:
            asset_ids.add(asset_id)
        wo_ts = _resolution_timestamp(metadata)
        if wo_ts:
            workorder_timestamps.append(wo_ts)

    if not evidence_event_ids and (not asset_ids or not workorder_timestamps):
        return []

    where_clauses = []
    params: List[Any] = []
    if evidence_event_ids:
        where_clauses.append("event_id = ANY(%s)")
        params.append(evidence_event_ids)
    if asset_ids and workorder_timestamps:
        min_ts = min(workorder_timestamps) - dt.timedelta(hours=fallback_window_h)
        max_ts = max(workorder_timestamps) + dt.timedelta(hours=fallback_window_h)
        where_clauses.append("(asset_id = ANY(%s) AND occurred_at BETWEEN %s AND %s)")
        params.extend([sorted(asset_ids), min_ts, max_ts])

    if org_scope_enabled(settings):
        where_clauses = [f"({clause})" for clause in where_clauses]
        where_clauses.append("org_id = %s")
        params.append(org_id)

    cur.execute(
        f"""
            SELECT event_id, asset_id, occurred_at
            FROM events
            WHERE {' OR '.join(where_clauses)}
        """,
        tuple(params),
    )
    return [
        {"event_id": row[0], "asset_id": row[1], "occurred_at": row[2]}
        for row in (cur.fetchall() or [])
    ]

def _rca_outcomes_report(window: int, access: TenantContext) -> Dict[str, Any]:
    if window > 365:
        raise HTTPException(status_code=400, detail="Window cannot exceed 365 days")
    s = Settings()
    try:
        conn = with_pg(s.pg_dsn)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    try:
        out: Dict[str, Any] = {}
        fallback_window_h = max(1, int(getattr(s, "ttr_fallback_window_h", 24) or 24))
        with conn, conn.cursor() as cur:
            fb_scope_sql, fb_scope_params = _org_scope_sql(s, access.org_id)
            # Feedback counts by action (accept/reject/edited)
            cur.execute(f"""
                SELECT action, COUNT(*) FROM rca_feedback
                WHERE created_at > {_window_clause(window)}
                {fb_scope_sql}
                GROUP BY action
            """, fb_scope_params)
            fb = {r[0]: int(r[1]) for r in cur.fetchall() if r and r[0]}
            total = sum(fb.values())
            accept = fb.get("accept", 0)
            out["feedback_counts"] = fb
            out["acceptance_rate"] = (accept / total) if total > 0 else None

            wo_scope_sql, wo_scope_params = _org_scope_sql(s, access.org_id, column="w.org_id")
            cur.execute(f"""
                SELECT w.asset_id, COUNT(*) AS n
                FROM workorders w
                WHERE COALESCE((w.metadata->>'created_at')::timestamptz, NOW()) > {_window_clause(window)}
                {wo_scope_sql}
                GROUP BY w.asset_id
                ORDER BY n DESC
                LIMIT 10
            """, wo_scope_params)
            out["top_assets_by_wo_volume"] = [{"asset_id": r[0], "count": int(r[1])} for r in cur.fetchall() if r]

            try:
                workorders = _fetch_workorders_for_ttr(cur, window, s, access.org_id)
                candidate_events = _fetch_candidate_events(cur, workorders, fallback_window_h, s, access.org_id)
                ttr_rows = _build_ttr_measurements(workorders, candidate_events, fallback_window_h)
            except Exception:
                ttr_rows = []

            ttrs = [row["ttr_seconds"] for row in ttr_rows]
            out["ttr_seconds_avg"] = (sum(ttrs) / len(ttrs)) if ttrs else None

        try:
            with conn, conn.cursor() as cur2:
                fb_scope_sql, fb_scope_params = _org_scope_sql(s, access.org_id)
                cur2.execute(f"""
                    SELECT asset_id,
                           COUNT(*) FILTER (WHERE action = 'accept') AS accept_cnt,
                           COUNT(*) AS total_cnt
                    FROM rca_feedback
                    WHERE created_at > {_window_clause(window)}
                    {fb_scope_sql}
                    GROUP BY asset_id
                """, fb_scope_params)
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

        if ttr_rows:
            per_asset_ttr: Dict[str, List[float]] = defaultdict(list)
            for row in ttr_rows:
                asset_id = row.get("asset_id")
                if asset_id:
                    per_asset_ttr[asset_id].append(row["ttr_seconds"])
            out["per_asset_ttr"] = [
                {
                    "asset_id": asset_id,
                    "ttr_seconds_avg": sum(values) / len(values),
                }
                for asset_id, values in sorted(
                    per_asset_ttr.items(),
                    key=lambda item: (sum(item[1]) / len(item[1])) if item[1] else -1,
                    reverse=True,
                )[:10]
            ]
        else:
            out["per_asset_ttr"] = None

        return out
    finally:
        conn.close()


@router.get("/rca-outcomes")
def rca_outcomes(
    window: int = Query(30, ge=1, le=365),
    access: TenantContext = Depends(require_role("viewer")),
) -> Dict[str, Any]:
    return _rca_outcomes_report(window, access)

@router.get("/rca-outcomes/csv")
def rca_outcomes_csv(
    window: int = Query(30, ge=1, le=365),
    access: TenantContext = Depends(require_role("viewer")),
):
    # Flatten a report view for leadership export
    rep = _rca_outcomes_report(window=window, access=access)
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