"""API router for reliability analytics (MTBF, MTTR, Availability).

Endpoints:
  GET /api/v1/reliability/equipment/{id}  — metrics for a single equipment unit
  GET /api/v1/reliability/asset/{id}      — metrics by legacy asset_id
  GET /api/v1/reliability/fleet           — fleet-wide metrics grouped by equipment
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request

from maintenance_intelligence.api.middleware.identity import (
    require_authenticated_identity,
    get_identity,
    get_identity_org_id,
)
from maintenance_intelligence.core.reliability.queries import (
    get_asset_reliability,
    get_equipment_reliability,
    get_fleet_reliability,
)

router = APIRouter(prefix="/api/v1/reliability", tags=["reliability"])


@router.get("/equipment/{equipment_unit_id}")
def equipment_reliability(
    request: Request,
    equipment_unit_id: str,
    window_days: int = Query(365, ge=1, le=1825, description="Observation window in days"),
):
    """MTBF, MTTR, availability, and failure rate for a single equipment unit."""
    require_authenticated_identity(
        request, detail="Reliability queries require an authenticated identity"
    )
    metrics = get_equipment_reliability(equipment_unit_id, window_days=window_days)
    return metrics.to_dict()


@router.get("/asset/{asset_id}")
def asset_reliability(
    request: Request,
    asset_id: str,
    window_days: int = Query(365, ge=1, le=1825),
):
    """MTBF, MTTR, availability for a legacy asset_id (backward compatible)."""
    require_authenticated_identity(
        request, detail="Reliability queries require an authenticated identity"
    )
    metrics = get_asset_reliability(asset_id, window_days=window_days)
    return metrics.to_dict()


@router.get("/fleet")
def fleet_reliability(
    request: Request,
    tenant_id: Optional[str] = Query(None),
    iso_equipment_class: Optional[str] = Query(None, description="Filter by ISO class, e.g. CENTRIFUGAL_PUMP"),
    equipment_family: Optional[str] = Query(None, description="Filter by family, e.g. EF-ROT"),
    window_days: int = Query(365, ge=1, le=1825),
):
    """Fleet-wide reliability metrics grouped by equipment unit."""
    require_authenticated_identity(
        request, detail="Reliability queries require an authenticated identity"
    )
    identity = get_identity(request)
    actor_org_id = get_identity_org_id(identity)
    if actor_org_id and tenant_id and tenant_id != actor_org_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Cross-tenant access is not permitted")
    if actor_org_id and not tenant_id:
        tenant_id = actor_org_id
    fleet = get_fleet_reliability(
        tenant_id=tenant_id,
        iso_equipment_class=iso_equipment_class,
        equipment_family=equipment_family,
        window_days=window_days,
    )
    return {
        "window_days": window_days,
        "equipment_count": len(fleet),
        "equipment": {k: v.to_dict() for k, v in fleet.items()},
    }
