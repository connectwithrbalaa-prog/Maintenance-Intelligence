import datetime as dt
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
import uuid
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.api.middleware.identity import (
    APPROVAL_ROLES,
    get_identity,
    get_identity_role,
    get_identity_subject,
    require_authenticated_identity,
)
from maintenance_intelligence.api.metrics import REGISTRY
from prometheus_client import Counter

router = APIRouter(prefix="/api/v1/rca", tags=["rca"])
feedback_total = Counter(
    "rca_feedback_total", "Total RCA feedback items", ["action"], registry=REGISTRY
)
connection_factory = with_pg


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _validate_lookup_id(value: str, field_name: str) -> str:
    candidate = value.strip()
    if (
        not candidate
        or candidate != value
        or len(candidate) > 255
        or any(ord(char) < 32 for char in candidate)
    ):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    return candidate


def _run_summary_root() -> Path:
    settings = Settings()
    return Path(settings.run_summary_dir).expanduser()


def _list_run_files(root: Path) -> List[Path]:
    if not root.exists() or not root.is_dir():
        return []
    return sorted(root.glob("*/*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def _load_payload(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _find_run_payload(run_id: str) -> Optional[Dict[str, Any]]:
    for path in _list_run_files(_run_summary_root()):
        payload = _load_payload(path)
        if payload is None:
            continue
        if run_id in {payload.get("run_id"), path.stem}:
            return payload
    return None


def _feedback_defaults(payload: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    if not isinstance(payload, dict):
        return {"recommendation_id": None, "org_id": None, "asset_id": None}
    context_meta = (
        payload.get("context_meta") if isinstance(payload.get("context_meta"), dict) else {}
    )
    return {
        "recommendation_id": _as_text(payload.get("recommendation_id"))
        or _as_text(payload.get("run_id")),
        "org_id": _as_text(payload.get("org_id")) or _as_text(context_meta.get("org_id")),
        "asset_id": _as_text(context_meta.get("asset_id")) or _as_text(payload.get("asset_id")),
    }


def _feedback_row_to_dict(row: Any) -> Dict[str, Any]:
    created_at = row[9] if len(row) > 9 else None
    return {
        "feedback_id": row[0],
        "run_id": row[1],
        "recommendation_id": row[2],
        "org_id": row[3],
        "asset_id": row[4],
        "action": row[5],
        "changes": row[6] or {},
        "reason": row[7],
        "user_id": row[8],
        "created_at": created_at.isoformat() if isinstance(created_at, dt.datetime) else created_at,
    }


def _identity_subject(request: Request) -> Optional[str]:
    identity = get_identity(request)
    return _as_text(get_identity_subject(identity)) if identity else None


def _authorize_feedback_submission(request: Request, claimed_user_id: Optional[str]) -> str:
    identity = get_identity(request)
    actor_id = _as_text(get_identity_subject(identity)) if identity else None
    actor_role = _as_text(get_identity_role(identity)) if identity else None
    if actor_id is None:
        raise HTTPException(
            status_code=403, detail="Feedback submission requires an authenticated identity"
        )
    if actor_role not in APPROVAL_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Feedback submission requires planner, maintainer, or admin role",
        )
    claimed_actor = _as_text(claimed_user_id)
    if claimed_actor is not None and claimed_actor != actor_id:
        raise HTTPException(
            status_code=403, detail="Feedback actor must match authenticated identity"
        )
    return actor_id


class FeedbackPayload(BaseModel):
    run_id: str = Field(..., description="Run id (event-level id in recommendation envelope)")
    recommendation_id: Optional[str] = Field(default=None, description="Recommendation id")
    action: str = Field(..., description="accept | reject | edited")
    changes: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    asset_id: Optional[str] = None


@router.post("/feedback")
def submit_feedback(p: FeedbackPayload, request: Request):
    if p.action not in ("accept", "reject", "edited"):
        raise HTTPException(status_code=400, detail="Invalid action")
    run_id = _validate_lookup_id(p.run_id, "run id")
    payload = _find_run_payload(run_id)
    defaults = _feedback_defaults(payload)
    recommendation_id = _as_text(p.recommendation_id) or defaults["recommendation_id"]
    if recommendation_id is None:
        raise HTTPException(status_code=400, detail="recommendation_id is required")
    actor_id = _authorize_feedback_submission(request, p.user_id)
    org_id = _as_text(p.org_id) or defaults["org_id"]
    asset_id = _as_text(p.asset_id) or defaults["asset_id"]

    s = Settings()
    try:
        conn = connection_factory(s.pg_dsn)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    try:
        fid = "FB-" + uuid.uuid4().hex[:12]
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rca_feedback(id, run_id, recommendation_id, org_id, asset_id, action, changes, reason, user_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                RETURNING id, run_id, recommendation_id, org_id, asset_id, action, changes, reason, user_id, created_at
                """,
                (
                    fid,
                    run_id,
                    recommendation_id,
                    org_id,
                    asset_id,
                    p.action,
                    json.dumps(p.changes) if p.changes is not None else None,
                    p.reason,
                    actor_id,
                ),
            )
            row = cur.fetchone()
        try:
            feedback_total.labels(action=p.action).inc()
        except Exception:
            pass
        return {"status": "ok", "feedback": _feedback_row_to_dict(row)}
    finally:
        conn.close()


@router.get("/feedback")
def list_feedback(
    request: Request,
    run_id: Optional[str] = Query(default=None),
    recommendation_id: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    require_authenticated_identity(
        request, detail="Feedback history requires an authenticated identity"
    )
    filters = []
    params: List[Any] = []

    if run_id is None and recommendation_id is None:
        raise HTTPException(status_code=400, detail="run_id or recommendation_id is required")

    if run_id is not None:
        filters.append("run_id = %s")
        params.append(_validate_lookup_id(run_id, "run id"))
    if recommendation_id is not None:
        filters.append("recommendation_id = %s")
        params.append(_validate_lookup_id(recommendation_id, "recommendation id"))
    if action is not None:
        if action not in ("accept", "reject", "edited"):
            raise HTTPException(status_code=400, detail="Invalid action")
        filters.append("action = %s")
        params.append(action)

    s = Settings()
    try:
        conn = connection_factory(s.pg_dsn)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    try:
        sql = """
            SELECT id, run_id, recommendation_id, org_id, asset_id, action, changes, reason, user_id, created_at
            FROM rca_feedback
            WHERE {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
        """.format(where_clause=" AND ".join(filters))
        with conn, conn.cursor() as cur:
            cur.execute(sql, tuple(params + [limit]))
            rows = cur.fetchall() or []
        return [_feedback_row_to_dict(row) for row in rows]
    finally:
        conn.close()
