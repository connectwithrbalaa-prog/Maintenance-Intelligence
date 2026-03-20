import json
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from maintenance_intelligence.cmms.adapter import (
    CMMSAdapterError,
    CMMSConfigurationError,
    CMMSPayloadError,
    CMMSRetryExhaustedError,
    CMMSUnavailableError,
    UnsupportedBackendError,
    cmms_failure_summary_from_error,
    create_cmms_adapter,
    discover_cmms_backends,
    normalize_work_order_lifecycle,
    normalize_cmms_failure_summary,
)
from maintenance_intelligence.api.middleware.identity import (
    ADMIN_ROLES,
    APPROVAL_ROLES,
    get_identity,
    get_identity_role,
    get_identity_subject,
    require_authenticated_identity,
    require_scoped_identity,
)
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.edge_command_buffer import EdgeCommandBuffer
from maintenance_intelligence.services.notifications import emit_notification
from maintenance_intelligence.services.wo_bridge import process_recommendation, with_pg

router = APIRouter(prefix="/api/v1/agents/pm", tags=["pm"])

QUEUED_OFFLINE_STATUS = "queued-offline"


class AnalyzePayload(BaseModel):
    run_id: str = Field(..., description="Run id to inspect for PM proposal generation")


class ApprovePayload(BaseModel):
    admin_retry: bool = Field(default=False, description="Whether this approval call is an admin-initiated retry")


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
            "failure_summary": normalize_cmms_failure_summary(detail=detail, handoff_state="failure"),
        }
    }


def _attempt_failure_summary(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return normalize_cmms_failure_summary(
        value.get("failure_summary"),
        detail=value.get("error_message") or value.get("detail"),
        handoff_state=value.get("handoff_state"),
    )


def _normalize_attempt_entry(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    attempt_number = value.get("attempt_number")
    attempted_at = _as_text(value.get("attempted_at"))
    approved_by = _as_text(value.get("approved_by"))
    approved_at = _as_text(value.get("approved_at"))
    handoff_state = _as_text(value.get("handoff_state")) or "pending"
    origin = _as_text(value.get("origin")) or "approval"
    connector_result = value.get("connector_result")
    if not isinstance(connector_result, dict):
        connector_result = value.get("result") if isinstance(value.get("result"), dict) else {}
    error_message = _as_text(value.get("error_message")) or _as_text(value.get("detail"))
    failure_summary = _attempt_failure_summary(value)
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
        "attempt_number": attempt_number,
        "attempted_at": attempted_at or "",
        "approved_by": approved_by or "",
        "approved_at": approved_at or "",
        "handoff_state": handoff_state,
        "origin": origin,
        "result": result,
        "connector_result": connector_result,
        "error_message": error_message or "",
        "failure_summary": failure_summary,
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


def _proposal_attempt_limit(settings: Settings) -> int:
    return max(1, int(settings.pm_handoff_max_attempts_per_proposal))


def _retry_fields(proposal: Dict[str, Any], max_attempts: int) -> Dict[str, Any]:
    attempts = proposal.get("approval_history") or _approval_attempts(proposal.get("metadata") or {})
    attempt_count = len(attempts)
    attempts_remaining = max(0, max_attempts - attempt_count)
    proposal_status = _as_text(proposal.get("status")) or "pending"
    latest_attempt = attempts[0] if attempts else {}
    latest_failure_summary = _attempt_failure_summary(latest_attempt)
    latest_retryable = True
    if (latest_attempt.get("handoff_state") or "") == "failure" and latest_failure_summary:
        latest_retryable = bool(latest_failure_summary.get("retryable"))
    retry_allowed = proposal_status not in {"approved", QUEUED_OFFLINE_STATUS} and attempts_remaining > 0 and latest_retryable
    return {
        "attempt_count": attempt_count,
        "attempts_remaining": attempts_remaining,
        "max_attempts": max_attempts,
        "retry_allowed": retry_allowed,
        "failure_summary": latest_failure_summary,
    }


def _proposal_with_retry_fields(proposal: Dict[str, Any], max_attempts: int) -> Dict[str, Any]:
    attempts = proposal.get("approval_history") or _approval_attempts(proposal.get("metadata") or {})
    latest_attempt = attempts[0] if attempts else {}
    proposal_status = _as_text(proposal.get("status")) or "pending"
    return {
        **proposal,
        **_retry_fields(proposal, max_attempts),
        "admin_retry_required": bool(attempts) and proposal_status not in {"approved", QUEUED_OFFLINE_STATUS} and _retry_fields(proposal, max_attempts)["retry_allowed"],
        "last_attempt_info": latest_attempt,
    }


def _connector_provenance_summary(
    proposal: Dict[str, Any],
    *,
    work_order_snapshot: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    proposal_id = _as_text(proposal.get("proposal_id")) or ""
    recommendation_id = _as_text(proposal.get("recommendation_id")) or proposal_id
    attempts = proposal.get("approval_history") or _approval_attempts(proposal.get("metadata") or {})
    latest_attempt = attempts[0] if attempts else {}
    connector_result = result if isinstance(result, dict) and result else latest_attempt.get("connector_result")
    if not isinstance(connector_result, dict):
        connector_result = {}
    snapshot = work_order_snapshot if isinstance(work_order_snapshot, dict) else {}
    snapshot_metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
    handoff = snapshot_metadata.get("handoff") if isinstance(snapshot_metadata.get("handoff"), dict) else {}
    handoff_lifecycle = handoff.get("lifecycle") if isinstance(handoff.get("lifecycle"), dict) else {}
    connector_lifecycle = connector_result.get("lifecycle") if isinstance(connector_result.get("lifecycle"), dict) else {}
    failure_summary = _attempt_failure_summary(latest_attempt)
    return {
        "proposal_id": proposal_id,
        "recommendation_id": recommendation_id,
        "origin": _as_text(handoff.get("origin")) or _as_text(latest_attempt.get("origin")) or "approval",
        "approved_by": _as_text(proposal.get("approved_by")) or _as_text(handoff.get("approved_by")) or _as_text(latest_attempt.get("approved_by")) or "",
        "recorded_at": _as_text(handoff.get("attempted_at")) or _as_text(handoff.get("approved_at")) or _as_text(latest_attempt.get("attempted_at")) or "",
        "attempt_count": len(attempts),
        "backend": _as_text(handoff.get("backend")) or _as_text(connector_result.get("backend")) or "",
        "connector_status": _as_text(connector_result.get("status")) or _as_text(proposal.get("handoff_state")) or _as_text(proposal.get("status")) or "pending",
        "connector_lifecycle_phase": _as_text(connector_result.get("lifecycle_phase")) or _as_text(connector_lifecycle.get("phase")) or _as_text(handoff.get("lifecycle_phase")) or _as_text(handoff_lifecycle.get("phase")) or "",
        "connector_terminal_state": bool(connector_result.get("terminal_state") or connector_lifecycle.get("terminal")),
        "work_order_id": _as_text(snapshot.get("wo_id")) or _as_text(proposal.get("work_order_id")) or _as_text(connector_result.get("wo_id")) or "",
        "work_order_status": _as_text(snapshot.get("status")) or _as_text(connector_result.get("status")) or "",
        "work_order_lifecycle_phase": _as_text(snapshot.get("lifecycle_phase")) or _as_text(snapshot.get("lifecycle", {}).get("phase") if isinstance(snapshot.get("lifecycle"), dict) else None) or _as_text(connector_result.get("lifecycle_phase")) or "",
        "work_order_terminal_state": bool(snapshot.get("terminal_state") or (snapshot.get("lifecycle", {}).get("terminal") if isinstance(snapshot.get("lifecycle"), dict) else False)),
        "transition_from": _as_text(handoff.get("status_before")) or "",
        "transition_to": _as_text(handoff.get("status_after")) or _as_text(snapshot.get("status")) or _as_text(connector_result.get("status")) or "",
        "failure_summary": failure_summary,
    }


def _work_order_snapshot_from_row(row: Any) -> Dict[str, Any]:
    metadata = row[8] if len(row) > 8 and isinstance(row[8], dict) else {}
    lifecycle = normalize_work_order_lifecycle(
        {
            "wo_id": row[0],
            "status": row[2],
            "workorder_created_at": row[5],
            "handoff_completed_at": row[6],
            "workorder_completed_at": row[7],
        }
    )
    return {
        "wo_id": row[0],
        "asset_id": row[1],
        "status": row[2],
        "title": row[3],
        "priority": row[4],
        "workorder_created_at": row[5],
        "handoff_completed_at": row[6],
        "workorder_completed_at": row[7],
        "lifecycle_phase": lifecycle["phase"],
        "terminal_state": lifecycle["terminal"],
        "lifecycle": lifecycle,
        "metadata": metadata,
    }


def _load_work_order_snapshots(conn: Any, work_order_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    filtered_ids = [work_order_id for work_order_id in work_order_ids if work_order_id]
    if not filtered_ids:
        return {}
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT wo_id, asset_id, status, title, priority, workorder_created_at,
                   handoff_completed_at, workorder_completed_at, metadata
            FROM workorders
            WHERE wo_id = ANY(%s)
            """,
            (filtered_ids,),
        )
        rows = cur.fetchall()
    snapshots: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not row or not row[0]:
            continue
        snapshots[str(row[0])] = _work_order_snapshot_from_row(row)
    return snapshots


def _attach_work_order_snapshots(proposals: List[Dict[str, Any]], snapshots: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for proposal in proposals:
        work_order_id = proposal.get("work_order_id")
        snapshot = snapshots.get(str(work_order_id), {}) if work_order_id else {}
        enriched.append({
            **proposal,
            "work_order_snapshot": snapshot,
            "connector_provenance_summary": _connector_provenance_summary(proposal, work_order_snapshot=snapshot),
        })
    return enriched


def _history_page(attempts: List[Dict[str, Any]], page: int, size: int) -> Dict[str, Any]:
    total_count = len(attempts)
    start = (page - 1) * size
    end = start + size
    return {
        "attempts": attempts[start:end],
        "total_count": total_count,
        "page": page,
        "size": size,
        "has_more": end < total_count,
    }


def _latest_connector_result(metadata: Any) -> Dict[str, Any]:
    attempts = _approval_attempts(metadata)
    if not attempts:
        return {}
    connector_result = attempts[0].get("connector_result")
    return connector_result if isinstance(connector_result, dict) else {}


def _append_approval_metadata(
    existing_metadata: Any,
    approved_by: Optional[str],
    attempts: List[Dict[str, Any]],
    *,
    origin: str = "approval",
) -> Dict[str, Any]:
    existing = existing_metadata if isinstance(existing_metadata, dict) else {}
    accumulated = list(reversed(_approval_attempts(existing)))
    normalized_attempts: List[Dict[str, Any]] = []
    for attempt in attempts:
        handoff_state = _as_text(attempt.get("handoff_state")) or "pending"
        attempted_at = _as_text(attempt.get("attempted_at")) or dt.datetime.now(dt.timezone.utc).isoformat()
        approved_at = _as_text(attempt.get("approved_at"))
        if approved_at is None and handoff_state == "success":
            approved_at = attempted_at
        normalized_attempts.append(
            {
                "attempt_number": attempt.get("attempt_number"),
                "attempted_at": attempted_at,
                "approved_by": approved_by,
                "approved_at": approved_at,
                "handoff_state": handoff_state,
                "origin": _as_text(attempt.get("origin")) or origin,
                "result": _as_text(attempt.get("result")) or ("success" if handoff_state == "success" else ("failure" if attempt.get("error_message") else "pending")),
                "connector_result": attempt.get("connector_result") if isinstance(attempt.get("connector_result"), dict) else {},
                "error_message": _as_text(attempt.get("error_message")) or "",
                "failure_summary": normalize_cmms_failure_summary(
                    attempt.get("failure_summary"),
                    detail=attempt.get("error_message"),
                    handoff_state=handoff_state,
                ),
            }
        )
    accumulated.extend(normalized_attempts)
    latest = normalized_attempts[-1] if normalized_attempts else (accumulated[-1] if accumulated else {
        "attempted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "approved_by": approved_by,
        "approved_at": None,
        "handoff_state": "pending",
        "result": "pending",
        "connector_result": {},
        "error_message": "",
        "failure_summary": {},
    })
    approval = {
        "approved_by": latest.get("approved_by"),
        "approved_at": latest.get("approved_at"),
        "attempted_at": latest.get("attempted_at"),
        "handoff_state": latest.get("handoff_state"),
        "origin": latest.get("origin") or origin,
        "result": latest.get("connector_result") or {},
        "detail": latest.get("error_message") or None,
        "failure_summary": _attempt_failure_summary(latest),
    }
    return {
        "approval": approval,
        "approval_attempts": accumulated,
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
    *,
    max_attempts: int,
    reused_result: bool = False,
    response_status: Optional[str] = None,
) -> JSONResponse:
    approval = _approval_fields(proposal.get("metadata") or {})
    approval_status = response_status or proposal.get("status") or ("approved" if result and result.get("handoff_complete") else "pending")
    approved_by = proposal.get("approved_by") or approval.get("approved_by")
    approved_at = proposal.get("approved_at") or approval.get("approved_at")
    normalized_proposal = {**proposal, "approved_by": approved_by, "approved_at": approved_at}
    handoff_state = normalized_proposal.get("handoff_state") or approval.get("handoff_state") or ("success" if approval_status == "approved" else "pending")
    attempts = normalized_proposal.get("approval_history") or _approval_attempts(normalized_proposal.get("metadata") or {})
    latest_attempt = attempts[0] if attempts else {}
    retry_fields = _retry_fields(normalized_proposal, max_attempts)
    failure_summary = _attempt_failure_summary(latest_attempt)
    body = {
        "status": approval_status,
        "handoff_state": handoff_state,
        "detail": detail,
        "approved": approval_status == "approved",
        "reused_result": reused_result,
        "attempt_count": retry_fields["attempt_count"],
        "attempts_remaining": retry_fields["attempts_remaining"],
        "max_attempts": retry_fields["max_attempts"],
        "retry_allowed": retry_fields["retry_allowed"],
        "failure_summary": failure_summary,
        "attempt_status": latest_attempt.get("handoff_state") or handoff_state,
        "last_attempt_info": latest_attempt,
        "admin_retry_required": bool(attempts) and approval_status not in {"approved", QUEUED_OFFLINE_STATUS} and retry_fields["retry_allowed"],
        "proposal_id": normalized_proposal.get("proposal_id"),
        "approved_by": approved_by,
        "approved_at": approved_at,
        "proposal": normalized_proposal,
        "work_order": result or {},
        "connector_provenance_summary": _connector_provenance_summary(normalized_proposal, result=result),
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
    return get_identity_subject(identity) if identity else None


def _role_from_request(request: Request) -> Optional[str]:
    identity = get_identity(request)
    return _as_text(get_identity_role(identity)) if identity else None


def _is_admin_role(role: Optional[str]) -> bool:
    return (role or "").strip().lower() in ADMIN_ROLES


def _is_approval_role(role: Optional[str]) -> bool:
    return (role or "").strip().lower() in APPROVAL_ROLES


def _proposal_scope(existing: Optional[Dict[str, Any]], payload: Optional[Dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    candidates: List[Dict[str, Any]] = []
    if isinstance(existing, dict):
        candidates.append(existing)
        metadata = existing.get("metadata")
        if isinstance(metadata, dict):
            candidates.append(metadata)
            context_meta = metadata.get("context_meta")
            if isinstance(context_meta, dict):
                candidates.append(context_meta)
    if isinstance(payload, dict):
        candidates.append(payload)
        context_meta = payload.get("context_meta")
        if isinstance(context_meta, dict):
            candidates.append(context_meta)

    org_id = None
    site_id = None
    for candidate in candidates:
        if org_id is None:
            org_id = _as_text(candidate.get("org_id"))
        if site_id is None:
            site_id = _as_text(candidate.get("site_id"))
        if org_id is not None and site_id is not None:
            break
    return org_id, site_id


def _emit_terminal_cmms_failure_notification(
    *,
    proposal_id: str,
    recommendation: Dict[str, Any],
    detail: str,
    failure_summary: Dict[str, Any],
    org_id: Optional[str],
    site_id: Optional[str],
) -> None:
    if not failure_summary or failure_summary.get("retryable"):
        return
    asset_id = _as_text(recommendation.get("asset_id")) or ""
    emit_notification(
        event_type="cmms.terminal_failure",
        severity="critical",
        summary=f"Terminal CMMS failure for proposal {proposal_id} on asset {asset_id or 'unknown'}",
        org_id=org_id,
        site_id=site_id,
        dedupe_key=f"cmms-terminal:{proposal_id}:{failure_summary.get('failure_class')}:{detail}",
        payload={
            "proposal_id": proposal_id,
            "recommendation_id": _as_text(recommendation.get("id")) or "",
            "asset_id": asset_id,
            "failure_summary": failure_summary,
            "detail": detail,
        },
    )


def _emit_cmms_exception_notification(
    *,
    proposal_id: str,
    recommendation: Dict[str, Any],
    detail: str,
    failure_summary: Dict[str, Any],
    org_id: Optional[str],
    site_id: Optional[str],
    queued_offline: bool = False,
) -> None:
    asset_id = _as_text(recommendation.get("asset_id")) or ""
    severity = "critical" if not failure_summary.get("retryable") else "warning"
    state = "queued-offline" if queued_offline else "pending"
    emit_notification(
        event_type="cmms.exception",
        severity=severity,
        summary=f"CMMS exception for proposal {proposal_id} on asset {asset_id or 'unknown'} ({state})",
        org_id=org_id,
        site_id=site_id,
        dedupe_key=f"cmms-exception:{proposal_id}:{failure_summary.get('failure_class')}:{state}:{detail}",
        payload={
            "proposal_id": proposal_id,
            "recommendation_id": _as_text(recommendation.get("id")) or "",
            "asset_id": asset_id,
            "failure_summary": failure_summary,
            "detail": detail,
            "queued_offline": queued_offline,
        },
    )


def _require_approval_actor(request: Request, *, org_id: Optional[str] = None, site_id: Optional[str] = None) -> tuple[str, str]:
    identity = require_scoped_identity(
        request,
        detail="PM approval requires an authenticated identity",
        allowed_roles=APPROVAL_ROLES,
        role_detail="PM approval requires planner, maintainer, or admin role",
        org_id=org_id,
        site_id=site_id,
        org_detail="PM approval is not authorized for this organization",
        site_detail="PM approval is not authorized for this site",
    )
    actor_id = _as_text(get_identity_subject(identity))
    actor_role = _as_text(get_identity_role(identity))
    if actor_id is None:
        raise HTTPException(status_code=403, detail="PM approval requires an authenticated identity")
    return actor_id, actor_role or ""


def _require_read_access(request: Request) -> None:
    require_authenticated_identity(request, detail="PM proposal reads require an authenticated identity")


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


def _queue_attempts(attempts: List[Dict[str, Any]], queued_result: Dict[str, Any], detail: str) -> List[Dict[str, Any]]:
    if attempts:
        queued_attempt = {
            **attempts[-1],
            "handoff_state": QUEUED_OFFLINE_STATUS,
            "result": "pending",
            "connector_result": queued_result,
            "error_message": detail,
            "failure_summary": normalize_cmms_failure_summary(detail=detail, handoff_state=QUEUED_OFFLINE_STATUS),
        }
        return [*attempts[:-1], queued_attempt]
    return [
        {
            "attempt_number": 1,
            "attempted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "handoff_state": QUEUED_OFFLINE_STATUS,
            "result": "pending",
            "connector_result": queued_result,
            "error_message": detail,
            "failure_summary": normalize_cmms_failure_summary(detail=detail, handoff_state=QUEUED_OFFLINE_STATUS),
        }
    ]


def _queue_offline_handoff(
    settings: Settings,
    proposal_id: str,
    recommendation: Dict[str, Any],
    approved_by: str,
    attempt_origin: str,
    detail: str,
    proposal: Dict[str, Any],
    attempts: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    queue = EdgeCommandBuffer(settings.edge_command_buffer_path)
    queued_command = queue.enqueue_command(
        proposal_id,
        {
            "proposal_id": proposal_id,
            "recommendation_id": recommendation.get("id"),
            "queued_from": "pm_advisor",
            "recommendation": recommendation,
            "handoff_context": {
                "proposal_id": proposal_id,
                "recommendation_id": recommendation.get("id"),
                "approved_by": approved_by,
                "origin": attempt_origin,
            },
        },
        error=detail,
    )
    queued_result = {
        "status": QUEUED_OFFLINE_STATUS,
        "handoff_complete": False,
        "backend": settings.pm_connector_backend,
        "proposal_id": proposal_id,
        "queue_id": queued_command.get("queue_id"),
        "queued_at": queued_command.get("queued_at"),
        "message": "CMMS handoff queued locally for replay",
        "reason": detail,
    }
    queue_attempts = _queue_attempts(attempts, queued_result, detail)
    conn = connection_factory(settings.pg_dsn)
    try:
        persisted = _update_proposal_status(
            conn,
            proposal_id,
            approved_by,
            None,
            QUEUED_OFFLINE_STATUS,
            _append_approval_metadata(proposal.get("metadata"), approved_by, queue_attempts, origin=attempt_origin),
        )
    finally:
        conn.close()
    return persisted, queued_result


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
    proposed_by, _actor_role = _require_approval_actor(request)
    found = _find_proposal_payload(payload.run_id)
    summary = found["payload"]
    source_path = found["source_path"]

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


@router.get("/connectors")
def list_connectors(request: Request) -> Dict[str, Any]:
    _require_read_access(request)
    settings = Settings()
    return {
        **discover_cmms_backends(settings),
        "selected_backend": settings.pm_connector_backend,
    }


@router.get("/proposals")
def list_proposals(request: Request) -> List[Dict[str, Any]]:
    _require_read_access(request)
    max_attempts = _proposal_attempt_limit(Settings())
    try:
        conn = _with_proposal_connection()
        try:
            persisted = _list_persisted_proposals(conn)
            if persisted:
                proposals = [_proposal_with_retry_fields(item, max_attempts) for item in persisted]
                snapshots = _load_work_order_snapshots(conn, [str(item.get("work_order_id") or "") for item in proposals])
                return _attach_work_order_snapshots(proposals, snapshots)
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
    return _attach_work_order_snapshots([_proposal_with_retry_fields(item, max_attempts) for item in items], {})


@router.get("/proposals/{proposal_id}/history")
def proposal_history(
    request: Request,
    proposal_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=3, ge=1, le=25),
) -> Dict[str, Any]:
    _require_read_access(request)
    settings = Settings()
    proposal = None
    try:
        proposal = _load_persisted_proposal(proposal_id)
    except Exception:
        proposal = None

    if proposal is None:
        found = _find_proposal_payload(proposal_id)
        proposal = _proposal_from_summary(found["payload"], found["source_path"])

    retry_fields = _retry_fields(proposal, _proposal_attempt_limit(settings))
    attempts = proposal.get("approval_history") or []
    paged = _history_page(attempts, page, size)
    return {
        "proposal_id": proposal.get("proposal_id") or proposal_id,
        "last_approver": proposal.get("last_approver"),
        "last_attempt_time": proposal.get("last_attempt_time"),
        "handoff_state": proposal.get("handoff_state") or "pending",
        "attempts": paged["attempts"],
        "total_count": paged["total_count"],
        "page": paged["page"],
        "size": paged["size"],
        "has_more": paged["has_more"],
        "attempt_count": retry_fields["attempt_count"],
        "attempts_remaining": retry_fields["attempts_remaining"],
        "max_attempts": retry_fields["max_attempts"],
        "retry_allowed": retry_fields["retry_allowed"],
    }


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: str, request: Request, approve_request: ApprovePayload = ApprovePayload()) -> Dict[str, Any]:
    found = _find_proposal_payload(proposal_id)
    payload = found["payload"]
    settings = Settings()
    max_attempts = _proposal_attempt_limit(settings)
    recommendation = _build_recommendation(payload)
    existing = None
    try:
        existing = _load_persisted_proposal(proposal_id)
    except Exception:
        existing = None

    proposal_org_id, proposal_site_id = _proposal_scope(existing, payload)
    approved_by, actor_role = _require_approval_actor(request, org_id=proposal_org_id, site_id=proposal_site_id)

    if existing and existing.get("status") == "approved" and existing.get("work_order_id"):
        return _approval_response(
            existing,
            _latest_connector_result(existing.get("metadata")),
            200,
            "PM proposal already approved; returning the existing handoff result",
            max_attempts=max_attempts,
            reused_result=True,
        )

    if existing and existing.get("status") == QUEUED_OFFLINE_STATUS:
        return _approval_response(
            existing,
            _latest_connector_result(existing.get("metadata")),
            202,
            "PM proposal already queued for offline handoff; returning the existing queue result",
            max_attempts=max_attempts,
            reused_result=True,
            response_status=QUEUED_OFFLINE_STATUS,
        )

    existing_attempts = _approval_attempts((existing or {}).get("metadata") or {})
    attempts_remaining = max(0, max_attempts - len(existing_attempts))
    latest_existing_attempt = existing_attempts[0] if existing_attempts else {}
    latest_failure_summary = _attempt_failure_summary(latest_existing_attempt)
    if attempts_remaining <= 0:
        raise HTTPException(status_code=409, detail=f"PM proposal reached the maximum of {max_attempts} handoff attempts")
    if latest_existing_attempt.get("handoff_state") == "failure" and latest_failure_summary and not latest_failure_summary.get("retryable", False):
        raise HTTPException(
            status_code=409,
            detail=f"Latest connector failure is terminal ({latest_failure_summary.get('failure_class')}); retry is not allowed",
        )

    manual_retry = bool(existing_attempts) and (existing or {}).get("status") != "approved"
    attempt_origin = "admin" if approve_request.admin_retry else "approval"
    if manual_retry:
        if not approve_request.admin_retry:
            raise HTTPException(status_code=403, detail="Manual retries require an admin or maintainer role")
        if not _is_admin_role(actor_role):
            raise HTTPException(status_code=403, detail="Admin retry requires admin or maintainer role")

    if not _recommendation_is_actionable(recommendation):
        raise HTTPException(status_code=422, detail="Proposal payload is malformed")

    proposal: Dict[str, Any] = {}
    try:
        conn = connection_factory(settings.pg_dsn)
        try:
            proposal = _proposal_record_from_summary(payload, found["source_path"])
            proposal = _upsert_proposal(conn, proposal)
            adapter = adapter_factory(settings)
            result = process_recommendation(
                {
                    "recommendation": recommendation,
                    "handoff_context": {
                        "proposal_id": proposal_id,
                        "recommendation_id": recommendation.get("id"),
                        "approved_by": approved_by,
                        "origin": attempt_origin,
                    },
                },
                conn,
                adapter,
                retry_attempts=(1 if settings.edge_mode_enabled else min(max(1, int(settings.pm_handoff_retry_attempts)), attempts_remaining)),
                retry_interval_s=settings.pm_handoff_retry_interval_s,
            )
            status = "approved" if result.get("handoff_complete") else "pending"
            persisted = _update_proposal_status(
                conn,
                proposal_id,
                approved_by,
                result.get("wo_id"),
                status,
                _append_approval_metadata(proposal.get("metadata"), approved_by, result.get("_attempts") or [], origin=attempt_origin),
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except UnsupportedBackendError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (CMMSPayloadError, CMMSConfigurationError) as exc:
        detail = str(exc)
        persisted: Dict[str, Any] = {}
        attempts = getattr(exc, "attempts", [])
        failure_summary = cmms_failure_summary_from_error(exc)
        try:
            conn = connection_factory(settings.pg_dsn)
            try:
                persisted = _update_proposal_status(
                    conn,
                    proposal_id,
                    approved_by,
                    None,
                    "pending",
                    _append_approval_metadata(proposal.get("metadata"), approved_by, attempts, origin=attempt_origin),
                )
            finally:
                conn.close()
        except Exception:
            pass
        _emit_terminal_cmms_failure_notification(
            proposal_id=proposal_id,
            recommendation=recommendation,
            detail=detail,
            failure_summary=failure_summary,
            org_id=proposal_org_id,
            site_id=proposal_site_id,
        )
        _emit_cmms_exception_notification(
            proposal_id=proposal_id,
            recommendation=recommendation,
            detail=detail,
            failure_summary=failure_summary,
            org_id=proposal_org_id,
            site_id=proposal_site_id,
            queued_offline=False,
        )
        return _approval_response(
            persisted or {"proposal_id": proposal_id, "status": "pending", "approved_by": approved_by, "approved_at": None},
            None,
            502,
            detail,
            max_attempts=max_attempts,
        )
    except CMMSRetryExhaustedError as exc:
        detail = str(exc)
        failure_summary = normalize_cmms_failure_summary(detail=detail, handoff_state="failure")
        if settings.edge_mode_enabled:
            try:
                persisted, queued_result = _queue_offline_handoff(
                    settings,
                    proposal_id,
                    recommendation,
                    approved_by,
                    attempt_origin,
                    detail,
                    proposal,
                    list(exc.attempts or []),
                )
                _emit_cmms_exception_notification(
                    proposal_id=proposal_id,
                    recommendation=recommendation,
                    detail=detail,
                    failure_summary=failure_summary,
                    org_id=proposal_org_id,
                    site_id=proposal_site_id,
                    queued_offline=True,
                )
                return _approval_response(
                    persisted,
                    queued_result,
                    202,
                    "PM proposal approved locally and queued for offline CMMS handoff",
                    max_attempts=max_attempts,
                    response_status=QUEUED_OFFLINE_STATUS,
                )
            except Exception:
                pass
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
                    _append_approval_metadata(proposal.get("metadata"), approved_by, exc.attempts, origin=attempt_origin),
                )
            finally:
                conn.close()
        except Exception:
            pass
        _emit_cmms_exception_notification(
            proposal_id=proposal_id,
            recommendation=recommendation,
            detail=detail,
            failure_summary=failure_summary,
            org_id=proposal_org_id,
            site_id=proposal_site_id,
            queued_offline=False,
        )
        return _approval_response(
            persisted or {"proposal_id": proposal_id, "status": "pending", "approved_by": approved_by, "approved_at": None},
            None,
            503,
            detail,
            max_attempts=max_attempts,
        )
    except CMMSAdapterError as exc:
        detail = str(exc)
        persisted = {}
        attempts = getattr(exc, "attempts", [])
        failure_summary = cmms_failure_summary_from_error(exc)
        if settings.edge_mode_enabled and failure_summary.get("retryable"):
            try:
                persisted, queued_result = _queue_offline_handoff(
                    settings,
                    proposal_id,
                    recommendation,
                    approved_by,
                    attempt_origin,
                    detail,
                    proposal,
                    list(attempts or []),
                )
                _emit_cmms_exception_notification(
                    proposal_id=proposal_id,
                    recommendation=recommendation,
                    detail=detail,
                    failure_summary=failure_summary,
                    org_id=proposal_org_id,
                    site_id=proposal_site_id,
                    queued_offline=True,
                )
                return _approval_response(
                    persisted,
                    queued_result,
                    202,
                    "PM proposal approved locally and queued for offline CMMS handoff",
                    max_attempts=max_attempts,
                    response_status=QUEUED_OFFLINE_STATUS,
                )
            except Exception:
                pass
        try:
            conn = connection_factory(settings.pg_dsn)
            try:
                persisted = _update_proposal_status(
                    conn,
                    proposal_id,
                    approved_by,
                    None,
                    "pending",
                    _append_approval_metadata(proposal.get("metadata"), approved_by, attempts, origin=attempt_origin),
                )
            finally:
                conn.close()
        except Exception:
            pass
        _emit_terminal_cmms_failure_notification(
            proposal_id=proposal_id,
            recommendation=recommendation,
            detail=detail,
            failure_summary=failure_summary,
            org_id=proposal_org_id,
            site_id=proposal_site_id,
        )
        _emit_cmms_exception_notification(
            proposal_id=proposal_id,
            recommendation=recommendation,
            detail=detail,
            failure_summary=failure_summary,
            org_id=proposal_org_id,
            site_id=proposal_site_id,
            queued_offline=False,
        )
        return _approval_response(
            persisted or {"proposal_id": proposal_id, "status": "pending", "approved_by": approved_by, "approved_at": None},
            None,
            503 if failure_summary.get("retryable") else 502,
            detail,
            max_attempts=max_attempts,
        )

    if result.get("handoff_complete"):
        return _approval_response(
            persisted,
            result,
            200,
            "PM proposal approved and handed off to the CMMS backend",
            max_attempts=max_attempts,
        )
    return _approval_response(
        persisted,
        result,
        202,
        "PM proposal saved, but the CMMS handoff is still pending",
        max_attempts=max_attempts,
    )