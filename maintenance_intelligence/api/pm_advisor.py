import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from maintenance_intelligence.api.auth import require_role
from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.multitenancy import TenantContext
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services.playbook_agent import search_playbooks
from maintenance_intelligence.services.pm_advisor_agent import analyze_pm_strategy
from maintenance_intelligence.services.wo_bridge import push_work_order_to_cms

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


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


@router.post("/pm/advisor/analyze")
def create_pm_proposal(
    payload: PMAdvisorRequest,
    access: TenantContext = Depends(require_role("operator")),
) -> Dict[str, Any]:
    recommendation = payload.model_dump()
    analysis = analyze_pm_strategy(recommendation, context=payload.metadata)
    playbooks = search_playbooks(
        analysis.get("playbook_query", payload.title), asset_id=payload.asset_id, limit=3
    )
    proposal_id = "PMP-" + uuid.uuid4().hex[:12]
    metadata = {**analysis.get("metadata", {}), **payload.metadata}

    conn = _db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pm_change_proposals(
                    proposal_id, org_id, run_id, recommendation_id, asset_id,
                    proposal_title, proposal_summary, recommended_actions,
                    playbook_refs, status, metadata
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb)
                """,
                (
                    proposal_id,
                    access.org_id,
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
        "analysis": analysis,
        "playbooks": playbooks,
    }


@router.post("/playbooks/search")
def search_playbook_library(
    payload: PlaybookSearchRequest,
    access: TenantContext = Depends(require_role("viewer")),
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
    access: TenantContext = Depends(require_role("viewer")),
) -> List[Dict[str, Any]]:
    conn = _db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT proposal_id, run_id, recommendation_id, asset_id, proposal_title,
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
                "proposal_id": row[0],
                "run_id": row[1],
                "recommendation_id": row[2],
                "asset_id": row[3],
                "proposal_title": row[4],
                "proposal_summary": row[5],
                "recommended_actions": row[6] or [],
                "playbook_refs": row[7] or [],
                "status": row[8],
                "approved_by": row[9],
                "approved_at": row[10].isoformat() if row[10] else None,
                "cms_reference": row[11],
                "metadata": row[12] or {},
                "created_at": row[13].isoformat() if row[13] else None,
                "updated_at": row[14].isoformat() if row[14] else None,
            }
        )
    return proposals


@router.post("/pm/proposals/{proposal_id}/approve")
def approve_pm_proposal(
    proposal_id: str,
    payload: ProposalApprovalRequest,
    access: TenantContext = Depends(require_role("operator")),
) -> Dict[str, Any]:
    conn = _db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT proposal_id, run_id, recommendation_id, asset_id, proposal_title,
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
                "proposal_id": row[0],
                "run_id": row[1],
                "recommendation_id": row[2],
                "asset_id": row[3],
                "proposal_title": row[4],
                "proposal_summary": row[5],
                "recommended_actions": row[6] or [],
                "playbook_refs": row[7] or [],
                "metadata": row[8] or {},
                "org_id": access.org_id,
            }
            cms_result = push_work_order_to_cms(
                proposal,
                approved_by=payload.approved_by or access.subject,
                notes=payload.notes,
            )
            cur.execute(
                """
                UPDATE pm_change_proposals
                SET status = %s,
                    approved_by = %s,
                    approved_at = NOW(),
                    cms_reference = %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE proposal_id = %s AND org_id = %s
                """,
                (
                    "approved",
                    payload.approved_by or access.subject,
                    cms_result.get("cms_reference"),
                    json.dumps({"approval_notes": payload.notes, "cms_result": cms_result}),
                    proposal_id,
                    access.org_id,
                ),
            )
    finally:
        conn.close()

    return {"proposal_id": proposal_id, "status": "approved", "cms_result": cms_result}