from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from maintenance_intelligence.api.middleware.identity import (
    APPROVAL_ROLES,
    get_identity,
    get_identity_role,
    get_identity_subject,
    require_authenticated_identity,
)
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services.repair_plan_service import (
    create_repair_plan,
    get_repair_plan,
    list_repair_plans,
    delete_repair_plan,
    add_part_to_plan,
    list_parts_for_plan,
)

router = APIRouter(prefix="/api/v1/repair-plans", tags=["repair-plan"])


class RepairPartSchema(BaseModel):
    part_id: Optional[str] = Field(
        default=None, description="Server-assigned repair part identifier"
    )
    plan_id: Optional[str] = Field(default=None, description="Parent repair plan identifier")
    name: Optional[str] = Field(default=None, description="Part name")
    description: Optional[str] = Field(default=None, description="Part description")
    quantity: Optional[int] = Field(default=None, description="Requested quantity", ge=1)
    unit: Optional[str] = Field(default=None, description="Quantity unit")
    metadata: Optional[dict[str, Any]] = Field(default=None, description="Freeform part metadata")
    created_at: Optional[str] = Field(
        default=None, description="Creation timestamp in ISO-8601 format"
    )


class RepairPlanSchema(BaseModel):
    plan_id: Optional[str] = Field(
        default=None, description="Server-assigned repair plan identifier"
    )
    run_id: Optional[str] = Field(
        default=None, description="RCA run identifier linked to this repair plan"
    )
    recommendation_id: Optional[str] = Field(
        default=None, description="Recommendation identifier linked to this repair plan"
    )
    org_id: Optional[str] = Field(default=None, description="Organization identifier")
    asset_id: Optional[str] = Field(default=None, description="Asset identifier")
    summary: Optional[str] = Field(default=None, description="Operator-facing repair summary")
    rationale: Optional[str] = Field(default=None, description="Why this repair plan was proposed")
    confidence: Optional[float] = Field(
        default=None, description="Model confidence between 0 and 1", ge=0, le=1
    )
    status: Optional[str] = Field(default=None, description="Current repair plan status")
    created_at: Optional[str] = Field(
        default=None, description="Creation timestamp in ISO-8601 format"
    )
    updated_at: Optional[str] = Field(
        default=None, description="Last update timestamp in ISO-8601 format"
    )


class RepairPlanDetailSchema(RepairPlanSchema):
    parts: list[RepairPartSchema] = Field(
        default_factory=list, description="Parts attached to this repair plan"
    )


class DeleteResponse(BaseModel):
    ok: bool = Field(description="Whether the delete completed")


def _settings() -> Settings:
    return Settings()


def _require_write_access(request: Request) -> str:
    identity = get_identity(request)
    actor_id = get_identity_subject(identity) if identity else None
    actor_role = get_identity_role(identity) if identity else None
    if actor_id is None:
        raise HTTPException(
            status_code=403, detail="Repair plan writes require an authenticated identity"
        )
    if actor_role not in APPROVAL_ROLES:
        raise HTTPException(
            status_code=403, detail="Repair plan writes require planner, maintainer, or admin role"
        )
    return actor_id


def _require_read_access(request: Request) -> None:
    require_authenticated_identity(
        request, detail="Repair plan reads require an authenticated identity"
    )


@router.post(
    "/",
    response_model=RepairPlanSchema,
    summary="Create a repair plan",
    description="Creates a repair plan record backed by the structured RCA output.",
)
def create(plan: RepairPlanSchema, request: Request):
    _require_write_access(request)
    settings = _settings()
    try:
        return create_repair_plan(
            settings.pg_dsn,
            run_id=plan.run_id,
            recommendation_id=plan.recommendation_id,
            org_id=plan.org_id,
            asset_id=plan.asset_id,
            summary=plan.summary,
            rationale=plan.rationale,
            confidence=plan.confidence,
            status=plan.status or "pending",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.get(
    "/{plan_id}",
    response_model=RepairPlanDetailSchema,
    summary="Get a repair plan",
    description="Returns a repair plan plus all parts attached to it.",
)
def get(plan_id: str, request: Request):
    _require_read_access(request)
    settings = _settings()
    try:
        obj = get_repair_plan(settings.pg_dsn, plan_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    if not obj:
        raise HTTPException(status_code=404, detail="Repair plan not found")
    try:
        parts = list_parts_for_plan(settings.pg_dsn, plan_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {**obj, "parts": parts}


@router.get(
    "/",
    response_model=list[RepairPlanSchema],
    summary="List repair plans",
    description="Lists recent repair plans ordered by creation time.",
)
def list_all(request: Request, limit: int = Query(default=100, ge=1, le=500)):
    _require_read_access(request)
    settings = _settings()
    try:
        return list_repair_plans(settings.pg_dsn, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.delete(
    "/{plan_id}",
    response_model=DeleteResponse,
    summary="Delete a repair plan",
    description="Deletes the repair plan and any attached parts.",
)
def delete(plan_id: str, request: Request):
    _require_write_access(request)
    settings = _settings()
    try:
        deleted = delete_repair_plan(settings.pg_dsn, plan_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Repair plan not found")
    return {"ok": True}


@router.post(
    "/{plan_id}/parts",
    response_model=RepairPartSchema,
    summary="Add a repair part",
    description="Attaches a required part to an existing repair plan.",
)
def add_part(plan_id: str, part: RepairPartSchema, request: Request):
    _require_write_access(request)
    settings = _settings()
    try:
        if not get_repair_plan(settings.pg_dsn, plan_id):
            raise HTTPException(status_code=404, detail="Repair plan not found")
        return add_part_to_plan(
            settings.pg_dsn,
            plan_id,
            name=part.name,
            description=part.description,
            quantity=part.quantity,
            unit=part.unit,
            metadata=part.metadata,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.get(
    "/{plan_id}/parts",
    response_model=list[RepairPartSchema],
    summary="List repair parts",
    description="Lists parts currently attached to a repair plan.",
)
def list_parts(plan_id: str, request: Request):
    _require_read_access(request)
    settings = _settings()
    try:
        if not get_repair_plan(settings.pg_dsn, plan_id):
            raise HTTPException(status_code=404, detail="Repair plan not found")
        return list_parts_for_plan(settings.pg_dsn, plan_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
