import json
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from maintenance_intelligence.cmms.adapter import (
    CMMSAdapterError,
    CMMSPayloadError,
    CMMSUnavailableError,
    UnsupportedBackendError,
    create_cmms_adapter,
)
from maintenance_intelligence.api.middleware.identity import get_identity
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services.wo_bridge import process_recommendation, with_pg

router = APIRouter(prefix="/api/v1/agents/pm", tags=["pm"])


class AnalyzePayload(BaseModel):
    run_id: str = Field(..., description="Run id to inspect for PM proposal generation")


connection_factory = with_pg
adapter_factory = create_cmms_adapter


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _approval_attempt_metadata(result: Optional[Dict[str, Any]], approved_by: Optional[str], status: str) -> Dict[str, Any]:
    attempted_at = dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "approval": {
            "approved_by": approved_by,
            "approved_at": attempted_at if status == "approved" else None,
            "attempted_at": attempted_at,
            "handoff_state": "success" if status == "approved" else "pending",
            "result": result or {},
        }
    }


def _approval_attempt_failure_metadata(
    approved_by: Optional[str],
    detail: str,
    status: str = "pending",
) -> Dict[str, Any]:
    attempted_at = dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "approval": {
            "approved_by": approved_by,
            "approved_at": None,
            "attempted_at": attempted_at,
            "handoff_state": "failure",
            "detail": detail,
            "result": {},
        }
    }


def _normalize_attempt_entry(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    attempted_at = _as_text(value.get("attempted_at"))
    approved_by = _as_text(value.get("approved_by"))
    approved_at = _as_text(value.get("approved_at"))
    handoff_state = _as_text(value.get("handoff_state")) or "pending"
    connector_result = value.get("connector_result")
    if not isinstance(connector_result, dict):
        connector_result = value.get("result") if isinstance(value.get("result"), dict) else {}
    error_message = _as_text(value.get("error_message")) or _as_text(value.get("detail"))
    result = _as_text(value.get("result"))
    if result not in {"success", "pending", "failure"}:
        if handoff_state == "success":
            result = "success"
        elif handoff_state == "failure" or error_message:
            result = "failure"
        else:
            result = "pending"
    if not attempted_at and not approved_by and not approved_at and not connector_result and not error_message:
        return None
    return {
        "attempted_at": attempted_at or "",
        "approved_by": approved_by or "",
        "approved_at": approved_at or "",
        "handoff_state": handoff_state,
        "result": result,
        "connector_result": connector_result,
        "error_message": error_message or "",
    }


def _approval_attempts(metadata: Any) -> List[Dict[str, Any]]:
    if not isinstance(metadata, dict):
        return []
    attempts = metadata.get("approval_attempts")
    normalized: List[Dict[str, Any]] = []
    if isinstance(attempts, list):
        for item in attempts:
            entry = _normalize_attempt_entry(item)
            if entry is not None:
                normalized.append(entry)
    if normalized:
        return list(reversed(normalized))
    fallback = _normalize_attempt_entry(metadata.get("approval"))
    return [fallback] if fallback is not None else []


def _proposal_audit_fields(metadata: Any) -> Dict[str, Any]:
    attempts = _approval_attempts(metadata)
    latest = attempts[0] if attempts else {}
    return {
        "approval_history": attempts,
        "last_approver": latest.get("approved_by"),
        "last_attempt_time": latest.get("attempted_at"),
        "handoff_state": latest.get("handoff_state") or "pending",
    }


def _append_approval_metadata(
    existing_metadata: Any,
    approved_by: Optional[str],
    status: str,
    connector_result: Optional[Dict[str, Any]] = None,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
    existing = existing_metadata if isinstance(existing_metadata, dict) else {}
    attempts = list(reversed(_approval_attempts(existing)))
    attempted_at = dt.datetime.now(dt.timezone.utc).isoformat()
    handoff_state = "failure" if detail else ("success" if status == "approved" else "pending")
    attempt = {
        "attempted_at": attempted_at,
        "approved_by": approved_by,
        "approved_at": attempted_at if status == "approved" else None,
        "handoff_state": handoff_state,
        "result": "failure" if detail else ("success" if status == "approved" else "pending"),
        "connector_result": connector_result or {},
        "error_message": detail,
    }
    attempts.append(attempt)
    approval = {
        "approved_by": approved_by,
        "approved_at": attempt["approved_at"],
        "attempted_at": attempted_at,
        "handoff_state": handoff_state,
        "result": connector_result or {},
        "detail": detail,
    }
    return {
        "approval": approval,
        "approval_attempts": attempts,
    }


def _approval_fields(metadata: Any) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    approval = metadata.get("approval")
    return approval if isinstance(approval, dict) else {}


def _approval_response(
    proposal: Dict[str, Any],
    result: Optional[Dict[str, Any]],
    status_code: int,
    detail: str,
) -> JSONResponse:
    approval = _approval_fields(proposal.get("metadata") or {})
    approval_status = proposal.get("status") or ("approved" if result and result.get("handoff_complete") else "pending")
    approved_by = proposal.get("approved_by") or approval.get("approved_by")
    approved_at = proposal.get("approved_at") or approval.get("approved_at")
    normalized_proposal = {**proposal, "approved_by": approved_by, "approved_at": approved_at}
    body = {
        "status": approval_status,
        "detail": detail,
        "approved": approval_status == "approved",
        "proposal_id": normalized_proposal.get("proposal_id"),
        "approved_by": approved_by,
        "approved_at": approved_at,
        "proposal": normalized_proposal,
        "work_order": result or {},
    }
    return JSONResponse(status_code=status_code, content=body)


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


def _identity_from_request(request: Request) -> Optional[str]:
    identity = get_identity(request)
    return identity.get("subject") if identity else None


def _proposal_from_summary(payload: Dict[str, Any], source_path: Path) -> Dict[str, Any]:
    structured = payload.get("structured") or {}
    context_meta = payload.get("context_meta") or {}
    metadata = payload.get("metadata") or {}
    approval = _approval_fields(metadata)
    return {
        "proposal_id": payload.get("recommendation_id") or payload.get("run_id") or source_path.stem,
        "run_id": payload.get("run_id") or source_path.stem,
        "recommendation_id": payload.get("recommendation_id"),
        "event_id": payload.get("event_id"),
        "title": structured.get("title") or "RCA Draft",
        "status": payload.get("status", "unknown"),
        "asset_id": context_meta.get("asset_id"),
        "confidence": structured.get("confidence"),
        "updated_at": source_path.stat().st_mtime,
        "source_file": source_path.name,
        "approved_by": approval.get("approved_by"),
        "approved_at": approval.get("approved_at"),
        "metadata": metadata,
        **_proposal_audit_fields(metadata),
    }


def _proposal_record_from_summary(payload: Dict[str, Any], source_path: Path, proposed_by: Optional[str] = None) -> Dict[str, Any]:
    structured = payload.get("structured") or {}
    context_meta = payload.get("context_meta") or {}
    rationale = "\n".join(structured.get("hypothesis") or []) or payload.get("summary") or "RCA proposal"
    return {
        "proposal_id": payload.get("recommendation_id") or payload.get("run_id") or source_path.stem,
        "run_id": payload.get("run_id") or source_path.stem,
        "recommendation_id": payload.get("recommendation_id"),
        "event_id": payload.get("event_id"),
        "asset_id": context_meta.get("asset_id"),
        "title": structured.get("title") or "RCA Draft",
        "rationale": rationale,
        "confidence": structured.get("confidence"),
        "status": "pending",
        "source_file": source_path.name,
        "proposed_by": proposed_by,
        "approved_by": None,
        "work_order_id": None,
        "metadata": {"model": payload.get("model") or {}, "context_meta": context_meta},
    }


def _build_recommendation(payload: Dict[str, Any]) -> Dict[str, Any]:
    structured = payload.get("structured") or {}
    context_meta = payload.get("context_meta") or {}
    rationale = "\n".join(structured.get("hypothesis") or []) or payload.get("summary") or "RCA proposal approval"
    return {
        "id": payload.get("recommendation_id") or payload.get("run_id"),
        "asset_id": context_meta.get("asset_id"),
        "title": structured.get("title") or "RCA Draft",
        "rationale": rationale,
        "priority": "MEDIUM",
        "model": payload.get("model") or {},
    }


def _recommendation_is_actionable(recommendation: Dict[str, Any]) -> bool:
    return bool(_as_text(recommendation.get("id")) and _as_text(recommendation.get("asset_id")))


def _find_proposal_payload(proposal_id: str) -> Dict[str, Any]:
    for path in _list_run_files(_run_summary_root()):
        payload = _load_payload(path)
        if payload is None:
            continue
        candidate_ids = {payload.get("recommendation_id"), payload.get("run_id"), path.stem}
        if proposal_id in candidate_ids:
            return {"payload": payload, "source_path": path}
    raise HTTPException(status_code=404, detail="Proposal not found")


def _proposal_from_row(row: Any) -> Dict[str, Any]:
    metadata = row[13] or {}
    approval = _approval_fields(metadata)
    return {
        "proposal_id": row[0],
        "run_id": row[1],
        "recommendation_id": row[2],
        "event_id": row[3],
        "asset_id": row[4],
        "title": row[5],
        "rationale": row[6],
        "confidence": row[7],
        "status": row[8],
        "source_file": row[9],
        "proposed_by": row[10],
        "approved_by": row[11],
        "approved_at": approval.get("approved_at"),
        "work_order_id": row[12],
        "metadata": metadata,
        **_proposal_audit_fields(metadata),
    }


def _upsert_proposal(conn, proposal: Dict[str, Any]) -> Dict[str, Any]:
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pm_proposals (
                proposal_id, run_id, recommendation_id, event_id, asset_id, title, rationale,
                confidence, status, source_file, proposed_by, approved_by, work_order_id, metadata
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (proposal_id) DO UPDATE SET
                run_id = EXCLUDED.run_id,
                recommendation_id = EXCLUDED.recommendation_id,
                event_id = EXCLUDED.event_id,
                asset_id = EXCLUDED.asset_id,
                title = EXCLUDED.title,
                rationale = EXCLUDED.rationale,
                confidence = EXCLUDED.confidence,
                source_file = EXCLUDED.source_file,
                proposed_by = COALESCE(pm_proposals.proposed_by, EXCLUDED.proposed_by),
                metadata = COALESCE(pm_proposals.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                updated_at = now()
            RETURNING proposal_id, run_id, recommendation_id, event_id, asset_id, title, rationale,
                      confidence, status, source_file, proposed_by, approved_by, work_order_id, metadata
            """,
            (
                proposal["proposal_id"],
                proposal["run_id"],
                proposal["recommendation_id"],
                proposal["event_id"],
                proposal["asset_id"],
                proposal["title"],
                proposal["rationale"],
                proposal["confidence"],
                proposal["status"],
                proposal["source_file"],
                proposal["proposed_by"],
                proposal["approved_by"],
                proposal["work_order_id"],
                json.dumps(proposal["metadata"]),
            ),
        )
        row = cur.fetchone()
    return _proposal_from_row(row)


def _list_persisted_proposals(conn) -> List[Dict[str, Any]]:
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT proposal_id, run_id, recommendation_id, event_id, asset_id, title, rationale,
                   confidence, status, source_file, proposed_by, approved_by, work_order_id, metadata
            FROM pm_proposals
            ORDER BY created_at DESC, proposal_id DESC
            """,
            (),
        )
        rows = cur.fetchall()
    return [_proposal_from_row(row) for row in rows]


def _update_proposal_status(
    conn,
    proposal_id: str,
    approved_by: Optional[str],
    work_order_id: Optional[str],
    status: str,
    metadata_update: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pm_proposals
            SET status = %s,
                approved_by = %s,
                work_order_id = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                updated_at = now()
            WHERE proposal_id = %s
            RETURNING proposal_id, run_id, recommendation_id, event_id, asset_id, title, rationale,
                      confidence, status, source_file, proposed_by, approved_by, work_order_id, metadata
            """,
            (status, approved_by, work_order_id, json.dumps(metadata_update or {}), proposal_id),
        )
        row = cur.fetchone()
    return _proposal_from_row(row) if row else {}


def _with_proposal_connection():
    settings = Settings()
    return connection_factory(settings.pg_dsn)


def _load_persisted_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    conn = _with_proposal_connection()
    try:
        for proposal in _list_persisted_proposals(conn):
            if proposal_id in {proposal.get("proposal_id"), proposal.get("recommendation_id"), proposal.get("run_id")}:
                return proposal
    finally:
        conn.close()
    return None


@router.post("/advisor/analyze")
def analyze_run(payload: AnalyzePayload, request: Request):
    found = _find_proposal_payload(payload.run_id)
    summary = found["payload"]
    source_path = found["source_path"]
    proposed_by = _identity_from_request(request)

    try:
        conn = _with_proposal_connection()
        try:
            proposal = _proposal_record_from_summary(summary, source_path, proposed_by=proposed_by)
            persisted = _upsert_proposal(conn, proposal)
        finally:
            conn.close()
    except Exception:
        persisted = _proposal_from_summary(summary, source_path)

    return {
        "status": "ok",
        "proposal": persisted,
        "requested_by": proposed_by,
    }


@router.get("/proposals")
def list_proposals() -> List[Dict[str, Any]]:
    try:
        conn = _with_proposal_connection()
        try:
            persisted = _list_persisted_proposals(conn)
            if persisted:
                return persisted
        finally:
            conn.close()
    except Exception:
        pass

    items: List[Dict[str, Any]] = []
    for path in _list_run_files(_run_summary_root()):
        payload = _load_payload(path)
        if payload is None:
            continue
        if not payload.get("recommendation_id") and not payload.get("run_id"):
            continue
        items.append(_proposal_from_summary(payload, path))
    return items


@router.get("/proposals/{proposal_id}/history")
def proposal_history(proposal_id: str) -> Dict[str, Any]:
    proposal = None
    try:
        proposal = _load_persisted_proposal(proposal_id)
    except Exception:
        proposal = None

    if proposal is None:
        found = _find_proposal_payload(proposal_id)
        proposal = _proposal_from_summary(found["payload"], found["source_path"])

    return {
        "proposal_id": proposal.get("proposal_id") or proposal_id,
        "last_approver": proposal.get("last_approver"),
        "last_attempt_time": proposal.get("last_attempt_time"),
        "handoff_state": proposal.get("handoff_state") or "pending",
        "attempts": proposal.get("approval_history") or [],
    }


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, request: Request) -> Dict[str, Any]:
    found = _find_proposal_payload(proposal_id)
    payload = found["payload"]
    settings = Settings()
    recommendation = _build_recommendation(payload)
    approved_by = _identity_from_request(request)

    if not _recommendation_is_actionable(recommendation):
        raise HTTPException(status_code=422, detail="Proposal payload is malformed")

    proposal: Dict[str, Any] = {}
    try:
        conn = connection_factory(settings.pg_dsn)
        try:
            proposal = _proposal_record_from_summary(payload, found["source_path"])
            proposal = _upsert_proposal(conn, proposal)
            adapter = adapter_factory(settings)
            result = process_recommendation({"recommendation": recommendation}, conn, adapter)
            status = "approved" if result.get("handoff_complete") else "pending"
            persisted = _update_proposal_status(
                conn,
                proposal_id,
                approved_by,
                result.get("wo_id"),
                status,
                _append_approval_metadata(proposal.get("metadata"), approved_by, status, connector_result=result),
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except UnsupportedBackendError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CMMSPayloadError as exc:
        detail = str(exc)
        persisted: Dict[str, Any] = {}
        try:
            conn = connection_factory(settings.pg_dsn)
            try:
                persisted = _update_proposal_status(
                    conn,
                    proposal_id,
                    approved_by,
                    None,
                    "pending",
                    _append_approval_metadata(proposal.get("metadata"), approved_by, "pending", detail=detail),
                )
            finally:
                conn.close()
        except Exception:
            pass
        return _approval_response(persisted or {"proposal_id": proposal_id, "status": "pending", "approved_by": approved_by, "approved_at": None}, None, 502, detail)
    except (CMMSUnavailableError, CMMSAdapterError) as exc:
        detail = str(exc)
        persisted = {}
        try:
            conn = connection_factory(settings.pg_dsn)
            try:
                persisted = _update_proposal_status(
                    conn,
                    proposal_id,
                    approved_by,
                    None,
                    "pending",
                    _append_approval_metadata(proposal.get("metadata"), approved_by, "pending", detail=detail),
                )
            finally:
                conn.close()
        except Exception:
            pass
        return _approval_response(persisted or {"proposal_id": proposal_id, "status": "pending", "approved_by": approved_by, "approved_at": None}, None, 503, detail)

    if result.get("handoff_complete"):
        return _approval_response(persisted, result, 200, "PM proposal approved and handed off to the CMMS backend")
    return _approval_response(persisted, result, 202, "PM proposal saved, but the CMMS handoff is still pending")