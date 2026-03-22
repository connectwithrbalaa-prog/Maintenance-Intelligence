"""API router for structured RAG context retrieval.

Endpoints:
  GET /api/v1/rag/context/{equipment_unit_id}  — full RCA context assembly
  GET /api/v1/rag/hierarchy/{equipment_unit_id} — hierarchy context only
  GET /api/v1/rag/failure-history/{equipment_unit_id} — failure history
  GET /api/v1/rag/taxonomy-lookup — ISO taxonomy lookup by codes
  GET /api/v1/rag/similar-failures — cross-fleet similar failures
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from maintenance_intelligence.ai.rag.structured_retriever import (
    assemble_rca_context,
    get_failure_history,
    get_hierarchy_context,
    get_iso_taxonomy_context,
    get_similar_equipment_failures,
)
from maintenance_intelligence.api.middleware.identity import (
    require_authenticated_identity,
)

router = APIRouter(prefix="/api/v1/rag", tags=["rag-context"])


@router.get("/context/{equipment_unit_id}")
def get_rca_context(
    request: Request,
    equipment_unit_id: str,
    failure_mode_code: Optional[str] = Query(None),
    failure_mechanism_code: Optional[str] = Query(None),
    failure_cause_code: Optional[str] = Query(None),
    window_days: int = Query(365, ge=1, le=1825),
):
    """Assemble full structured RCA context for an equipment unit.

    Returns hierarchy, failure history, ISO taxonomy, similar fleet failures,
    and reliability metrics — ready for GenAI prompt injection.
    """
    require_authenticated_identity(
        request, detail="RAG context queries require an authenticated identity"
    )
    ctx = assemble_rca_context(
        equipment_unit_id,
        failure_mode_code=failure_mode_code,
        failure_mechanism_code=failure_mechanism_code,
        failure_cause_code=failure_cause_code,
        window_days=window_days,
    )
    return {
        "equipment_unit_id": equipment_unit_id,
        "hierarchy": ctx.hierarchy.__dict__ if ctx.hierarchy else None,
        "failure_history_count": len(ctx.failure_history),
        "failure_history": [
            {
                "event_id": e.event_id,
                "failure_mode_code": e.failure_mode_code,
                "failure_mechanism_code": e.failure_mechanism_code,
                "failure_cause_code": e.failure_cause_code,
                "summary": e.summary,
                "downtime_hours": e.downtime_hours,
                "severity": e.severity,
            }
            for e in ctx.failure_history
        ],
        "iso_taxonomy": {
            "failure_mode": ctx.iso_taxonomy.failure_mode if ctx.iso_taxonomy else None,
            "failure_mechanism": ctx.iso_taxonomy.failure_mechanism if ctx.iso_taxonomy else None,
            "failure_cause": ctx.iso_taxonomy.failure_cause if ctx.iso_taxonomy else None,
        } if ctx.iso_taxonomy else None,
        "similar_failures_count": len(ctx.similar_failures),
        "similar_failures": [
            {
                "event_id": e.event_id,
                "failure_mode_code": e.failure_mode_code,
                "summary": e.summary,
            }
            for e in ctx.similar_failures
        ],
        "reliability_summary": ctx.reliability_summary,
        "prompt_text": ctx.to_prompt_text(),
    }


@router.get("/hierarchy/{equipment_unit_id}")
def get_hierarchy(request: Request, equipment_unit_id: str):
    """Get ISO 14224 hierarchy context for an equipment unit."""
    require_authenticated_identity(
        request, detail="RAG context queries require an authenticated identity"
    )
    ctx = get_hierarchy_context(equipment_unit_id)
    if not ctx:
        return {"equipment_unit_id": equipment_unit_id, "found": False}
    return {"found": True, **ctx.__dict__, "prompt_text": ctx.to_prompt_text()}


@router.get("/failure-history/{equipment_unit_id}")
def get_failures(
    request: Request,
    equipment_unit_id: str,
    window_days: int = Query(365, ge=1, le=1825),
    limit: int = Query(20, ge=1, le=100),
):
    """Get ISO-coded failure history for an equipment unit."""
    require_authenticated_identity(
        request, detail="RAG context queries require an authenticated identity"
    )
    entries = get_failure_history(equipment_unit_id, window_days=window_days, limit=limit)
    return {
        "equipment_unit_id": equipment_unit_id,
        "count": len(entries),
        "entries": [
            {
                "event_id": e.event_id,
                "failure_mode_code": e.failure_mode_code,
                "failure_mechanism_code": e.failure_mechanism_code,
                "failure_cause_code": e.failure_cause_code,
                "maintenance_action_code": e.maintenance_action_code,
                "summary": e.summary,
                "downtime_hours": e.downtime_hours,
                "severity": e.severity,
            }
            for e in entries
        ],
    }


@router.get("/taxonomy-lookup")
def taxonomy_lookup(
    request: Request,
    failure_mode_code: Optional[str] = Query(None),
    failure_mechanism_code: Optional[str] = Query(None),
    failure_cause_code: Optional[str] = Query(None),
    maintenance_action_code: Optional[str] = Query(None),
    detection_method_code: Optional[str] = Query(None),
):
    """Look up ISO 14224 taxonomy reference data by codes."""
    require_authenticated_identity(
        request, detail="RAG context queries require an authenticated identity"
    )
    ctx = get_iso_taxonomy_context(
        failure_mode_code=failure_mode_code,
        failure_mechanism_code=failure_mechanism_code,
        failure_cause_code=failure_cause_code,
        maintenance_action_code=maintenance_action_code,
        detection_method_code=detection_method_code,
    )
    return {
        "failure_mode": ctx.failure_mode,
        "failure_mechanism": ctx.failure_mechanism,
        "failure_cause": ctx.failure_cause,
        "maintenance_action": ctx.maintenance_action,
        "detection_method": ctx.detection_method,
        "prompt_text": ctx.to_prompt_text(),
    }


@router.get("/similar-failures")
def similar_failures(
    request: Request,
    iso_equipment_class: str = Query(..., description="e.g. CENTRIFUGAL_PUMP"),
    failure_mode_code: Optional[str] = Query(None),
    exclude_equipment_id: Optional[str] = Query(None),
    window_days: int = Query(365, ge=1, le=1825),
    limit: int = Query(10, ge=1, le=50),
):
    """Find failures on similar equipment across the fleet."""
    require_authenticated_identity(
        request, detail="RAG context queries require an authenticated identity"
    )
    entries = get_similar_equipment_failures(
        iso_equipment_class,
        failure_mode_code=failure_mode_code,
        exclude_equipment_id=exclude_equipment_id,
        window_days=window_days,
        limit=limit,
    )
    return {
        "iso_equipment_class": iso_equipment_class,
        "failure_mode_code": failure_mode_code,
        "count": len(entries),
        "entries": [
            {
                "event_id": e.event_id,
                "failure_mode_code": e.failure_mode_code,
                "summary": e.summary,
                "downtime_hours": e.downtime_hours,
            }
            for e in entries
        ],
    }
