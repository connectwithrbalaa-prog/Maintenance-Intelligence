"""API router for ISO 14224 taxonomy reference data.

Read-only endpoints for failure modes, mechanisms, causes,
maintenance actions, detection methods, and equipment family configs.

Endpoints:
  GET /api/v1/taxonomy/failure-modes
  GET /api/v1/taxonomy/failure-mechanisms
  GET /api/v1/taxonomy/failure-causes
  GET /api/v1/taxonomy/maintenance-actions
  GET /api/v1/taxonomy/detection-methods
  GET /api/v1/taxonomy/equipment-families
  GET /api/v1/taxonomy/equipment-families/{family_code}
  GET /api/v1/taxonomy/process-templates
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import APIRouter, HTTPException, Query, Request

from maintenance_intelligence.api.middleware.identity import (
    require_authenticated_identity,
)
from maintenance_intelligence.core.taxonomy.equipment_families import (
    EQUIPMENT_FAMILIES,
    PROCESS_TEMPLATES,
)
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1/taxonomy", tags=["taxonomy"])


def _pg(settings: Optional[Settings] = None):
    s = settings or Settings()
    return psycopg2.connect(s.pg_dsn)


def _rows(conn, query: str, params=None) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(query, params or ())
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── ISO 14224 failure classification ──


@router.get("/failure-modes")
def list_failure_modes(
    request: Request,
    equipment_family: Optional[str] = Query(None, description="Filter by equipment family, e.g. EF-ROT"),
):
    require_authenticated_identity(
        request, detail="Taxonomy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        rows = _rows(conn, "SELECT * FROM iso_failure_modes ORDER BY code")
        if equipment_family:
            rows = [
                r for r in rows
                if not r.get("applicable_equipment_families")
                or equipment_family in (r["applicable_equipment_families"] or "")
            ]
        return rows
    finally:
        conn.close()


@router.get("/failure-mechanisms")
def list_failure_mechanisms(request: Request):
    require_authenticated_identity(
        request, detail="Taxonomy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        return _rows(conn, "SELECT * FROM iso_failure_mechanisms ORDER BY code")
    finally:
        conn.close()


@router.get("/failure-causes")
def list_failure_causes(
    request: Request,
    category: Optional[str] = Query(None, description="Filter by category: DESIGN, OPERATION, MAINTENANCE, etc."),
):
    require_authenticated_identity(
        request, detail="Taxonomy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        if category:
            return _rows(
                conn,
                "SELECT * FROM iso_failure_causes WHERE category = %s ORDER BY code",
                (category.upper(),),
            )
        return _rows(conn, "SELECT * FROM iso_failure_causes ORDER BY code")
    finally:
        conn.close()


@router.get("/maintenance-actions")
def list_maintenance_actions(
    request: Request,
    maintenance_category: Optional[str] = Query(None, description="CORRECTIVE, PREVENTIVE, DETECTIVE"),
):
    require_authenticated_identity(
        request, detail="Taxonomy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        if maintenance_category:
            return _rows(
                conn,
                "SELECT * FROM iso_maintenance_actions WHERE maintenance_category = %s ORDER BY code",
                (maintenance_category.upper(),),
            )
        return _rows(conn, "SELECT * FROM iso_maintenance_actions ORDER BY code")
    finally:
        conn.close()


@router.get("/detection-methods")
def list_detection_methods(request: Request):
    require_authenticated_identity(
        request, detail="Taxonomy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        return _rows(conn, "SELECT * FROM iso_detection_methods ORDER BY code")
    finally:
        conn.close()


# ── Equipment family configs (from Python config, not DB) ──


@router.get("/equipment-families")
def list_equipment_families(request: Request):
    require_authenticated_identity(
        request, detail="Taxonomy queries require an authenticated identity"
    )
    return {
        code: {
            "code": code,
            "name": fam["name"],
            "description": fam["description"],
            "equipment_classes": fam["equipment_classes"],
            "subunit_types": fam["subunit_types"],
            "component_types": fam["component_types"],
        }
        for code, fam in EQUIPMENT_FAMILIES.items()
    }


@router.get("/equipment-families/{family_code}")
def get_equipment_family(request: Request, family_code: str):
    require_authenticated_identity(
        request, detail="Taxonomy queries require an authenticated identity"
    )
    fam = EQUIPMENT_FAMILIES.get(family_code.upper())
    if not fam:
        raise HTTPException(status_code=404, detail=f"Equipment family {family_code} not found")
    return {
        "code": family_code.upper(),
        "name": fam["name"],
        "description": fam["description"],
        "equipment_classes": fam["equipment_classes"],
        "subunit_types": fam["subunit_types"],
        "component_types": fam["component_types"],
    }


@router.get("/process-templates")
def list_process_templates(request: Request):
    require_authenticated_identity(
        request, detail="Taxonomy queries require an authenticated identity"
    )
    return {
        code: {
            "code": code,
            "name": tmpl["name"],
            "facility_types": tmpl["facility_types"],
            "system_types": tmpl["system_types"],
        }
        for code, tmpl in PROCESS_TEMPLATES.items()
    }
