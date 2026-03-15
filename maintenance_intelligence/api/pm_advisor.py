import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.multitenancy import TenantContext, normalize_role, role_allows
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.api.whoami import resolve_request_identity
from maintenance_intelligence.services.cmms import CMMSConnectorPayloadError, CMMSConnectorUnavailableError
from maintenance_intelligence.services.playbook_agent import normalize_playbook_results, search_playbooks
from maintenance_intelligence.services.pm_advisor_agent import analyze_pm_strategy
from maintenance_intelligence.services.wo_bridge import push_work_order_to_cms

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for item in value:
        text = _as_text(item)
        if text is not None:
            items.append(text)
    return items


def _as_playbook_refs(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            refs.append(item)
    return refs


def _isoformat(value: Any) -> Optional[str]:
    return value.isoformat() if value else None


def _normalize_playbook_refs(value: Any, asset_id: Optional[str]) -> List[Dict[str, Any]]:
    return normalize_playbook_results(value, asset_id=asset_id)


def _proposal_is_actionable(proposal: Dict[str, Any]) -> bool:
    return bool(proposal.get("proposal_id") and proposal.get("asset_id"))


def _approval_metadata(notes: Optional[str], cms_result: Optional[Dict[str, Any]], status: str) -> Dict[str, Any]:
    return {
        "approval_notes": notes,
        "cms_result": cms_result or {},
        "handoff_state": status,
    }


def _persist_approval_result(
    cur,
    *,
    proposal_id: str,
    org_id: str,
    status: str,
    approved_by: Optional[str],
    cms_reference: Optional[str],
    metadata: Dict[str, Any],
) -> None:
    cur.execute(
        """
        UPDATE pm_change_proposals
        SET status = %s,
            approved_by = %s,
            approved_at = CASE WHEN %s = 'approved' THEN NOW() ELSE approved_at END,
            cms_reference = %s,
            metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
            updated_at = NOW()
        WHERE proposal_id = %s AND org_id = %s
        """,
        (
            status,
            approved_by,
            status,
            cms_reference,
            json.dumps(metadata),
            proposal_id,
            org_id,
        ),
    )


class PMAdvisorRequest(BaseModel):
    run_id: str
    recommendation_id: str
    asset_id: str
    title: str
    rationale: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)
    immediate_actions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlaybookSearchRequest(BaseModel):
    query: str
    asset_id: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=20)


class ProposalApprovalRequest(BaseModel):
    approved_by: Optional[str] = None
    notes: Optional[str] = None


def _db_connection():
    settings = Settings()
    try:
        return with_pg(settings.pg_dsn)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


def require_pm_identity(minimum_role: str):
    minimum_role = normalize_role(minimum_role)

    def dependency(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
        x_role: str | None = Header(default=None, alias="X-Role"),
        x_subject: str | None = Header(default=None, alias="X-Subject"),
    ) -> TenantContext:
        access = resolve_request_identity(
            request,
            x_api_key=x_api_key,
            x_org_id=x_org_id,
            x_role=x_role,
            x_subject=x_subject,
        )
        if access is None:
            raise HTTPException(status_code=401, detail="Authenticated identity required")
        if not role_allows(access.role, minimum_role):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return access

    return dependency


@router.post("/pm/advisor/analyze")
def create_pm_proposal(
    payload: PMAdvisorRequest,
    access: TenantContext = Depends(require_pm_identity("operator")),
) -> Dict[str, Any]:
    recommendation = payload.model_dump()
    analysis = analyze_pm_strategy(
        recommendation,
        context=payload.metadata,
        identity={"org_id": access.org_id, "role": access.role, "subject": access.subject},
    )
    playbooks = _normalize_playbook_refs(
        search_playbooks(analysis.get("playbook_query", payload.title), asset_id=payload.asset_id, limit=3),
        asset_id=payload.asset_id,
    )
    proposal_id = "PMP-" + uuid.uuid4().hex[:12]
    metadata = {**analysis.get("metadata", {}), **payload.metadata}

    conn = _db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pm_change_proposals(
                    proposal_id, org_id, proposer_subject, run_id, recommendation_id, asset_id,
                    proposal_title, proposal_summary, recommended_actions,
                    playbook_refs, status, metadata
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb)
                """,
                (
                    proposal_id,
                    access.org_id,
                    access.subject,
                    payload.run_id,
                    payload.recommendation_id,
                    payload.asset_id,
                    analysis["proposal_title"],
                    analysis["proposal_summary"],
                    json.dumps(analysis.get("recommended_actions", [])),
                    json.dumps(playbooks),
                    "draft",
                    json.dumps(metadata),
                ),
            )
    finally:
        conn.close()

    return {
        "proposal_id": proposal_id,
        "status": "draft",
        "org_id": access.org_id,
        "proposer_subject": access.subject,
        "analysis": analysis,
        "playbooks": playbooks,
    }


@router.post("/playbooks/search")
def search_playbook_library(
    payload: PlaybookSearchRequest,
    access: TenantContext = Depends(require_pm_identity("viewer")),
) -> Dict[str, Any]:
    return {
        "org_id": access.org_id,
        "query": payload.query,
        "results": search_playbooks(payload.query, asset_id=payload.asset_id, limit=payload.limit),
    }


@router.get("/pm/proposals")
def list_pm_proposals(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    access: TenantContext = Depends(require_pm_identity("viewer")),
) -> List[Dict[str, Any]]:
    conn = _db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                  SELECT proposal_id, org_id, proposer_subject, run_id, recommendation_id, asset_id, proposal_title,
                       proposal_summary, recommended_actions, playbook_refs, status,
                       approved_by, approved_at, cms_reference, metadata, created_at, updated_at
                FROM pm_change_proposals
                WHERE org_id = %s AND (%s IS NULL OR status = %s)
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (access.org_id, status, status, limit),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    proposals: List[Dict[str, Any]] = []
    for row in rows:
        proposals.append(
            {
                "proposal_id": _as_text(row[0]),
                "org_id": _as_text(row[1]),
                "proposer_subject": _as_text(row[2]),
                "run_id": _as_text(row[3]),
                "recommendation_id": _as_text(row[4]),
                "asset_id": _as_text(row[5]),
                "proposal_title": _as_text(row[6]),
                "proposal_summary": _as_text(row[7]),
                "recommended_actions": _as_string_list(row[8]),
                "playbook_refs": _as_playbook_refs(row[9]),
                "status": _as_text(row[10]) or "unknown",
                "approved_by": _as_text(row[11]),
                "approved_at": _isoformat(row[12]),
                "cms_reference": _as_text(row[13]),
                "metadata": _as_dict(row[14]),
                "created_at": _isoformat(row[15]),
                "updated_at": _isoformat(row[16]),
            }
        )
    return proposals


@router.post("/pm/proposals/{proposal_id}/approve")
def approve_pm_proposal(
    proposal_id: str,
    payload: ProposalApprovalRequest,
    access: TenantContext = Depends(require_pm_identity("operator")),
) -> Dict[str, Any]:
    conn = _db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                  SELECT proposal_id, org_id, proposer_subject, run_id, recommendation_id, asset_id, proposal_title,
                      proposal_summary, recommended_actions, playbook_refs, metadata
                FROM pm_change_proposals
                WHERE proposal_id = %s AND org_id = %s
                """,
                (proposal_id, access.org_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Proposal not found")

            proposal = {
                "proposal_id": _as_text(row[0]),
                "org_id": _as_text(row[1]),
                "proposer_subject": _as_text(row[2]),
                "run_id": _as_text(row[3]),
                "recommendation_id": _as_text(row[4]),
                "asset_id": _as_text(row[5]),
                "proposal_title": _as_text(row[6]),
                "proposal_summary": _as_text(row[7]),
                "recommended_actions": _as_string_list(row[8]),
                "playbook_refs": _as_playbook_refs(row[9]),
                "metadata": _as_dict(row[10]),
            }
            if not _proposal_is_actionable(proposal):
                _persist_approval_result(
                    cur,
                    proposal_id=proposal_id,
                    org_id=access.org_id,
                    status="pending",
                    approved_by=payload.approved_by or access.subject,
                    cms_reference=None,
                    metadata=_approval_metadata(payload.notes, None, "pending"),
                )
                raise HTTPException(status_code=422, detail="Proposal payload is malformed")
            try:
                cms_result = push_work_order_to_cms(
                    proposal,
                    approved_by=payload.approved_by or access.subject,
                    notes=payload.notes,
                )
            except CMMSConnectorPayloadError as exc:
                _persist_approval_result(
                    cur,
                    proposal_id=proposal_id,
                    org_id=access.org_id,
                    status="pending",
                    approved_by=payload.approved_by or access.subject,
                    cms_reference=None,
                    metadata=_approval_metadata(payload.notes, None, "pending"),
                )
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except (CMMSConnectorUnavailableError, ValueError) as exc:
                _persist_approval_result(
                    cur,
                    proposal_id=proposal_id,
                    org_id=access.org_id,
                    status="pending",
                    approved_by=payload.approved_by or access.subject,
                    cms_reference=None,
                    metadata=_approval_metadata(payload.notes, None, "pending"),
                )
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            approval_status = "approved" if cms_result.get("handoff_complete") else "pending"
            _persist_approval_result(
                cur,
                proposal_id=proposal_id,
                org_id=access.org_id,
                status=approval_status,
                approved_by=payload.approved_by or access.subject,
                cms_reference=cms_result.get("cms_reference"),
                metadata=_approval_metadata(payload.notes, cms_result, approval_status),
            )
    finally:
        conn.close()

    response = {
        "proposal_id": proposal_id,
        "status": "approved" if cms_result.get("handoff_complete") else "pending",
        "org_id": access.org_id,
        "proposer_subject": proposal.get("proposer_subject"),
        "cms_result": cms_result,
    }
    if cms_result.get("handoff_complete"):
        return response
    return JSONResponse(status_code=202, content=response)