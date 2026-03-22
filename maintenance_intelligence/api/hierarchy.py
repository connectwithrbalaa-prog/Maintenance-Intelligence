"""API router for the ISO 14224 asset hierarchy (L1–L8).

Endpoints:
  GET  /api/v1/hierarchy/sites           — list sites
  GET  /api/v1/hierarchy/facilities      — list facilities for a site
  GET  /api/v1/hierarchy/systems         — list systems for a facility
  GET  /api/v1/hierarchy/equipment       — list equipment units (filterable)
  GET  /api/v1/hierarchy/equipment/{id}  — get single equipment unit
  GET  /api/v1/hierarchy/equipment/{id}/path — full hierarchy path (L1→L6)
  POST /api/v1/hierarchy/equipment       — upsert equipment unit
  GET  /api/v1/hierarchy/subunits        — list subunits for equipment
  GET  /api/v1/hierarchy/components      — list components for subunit
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from maintenance_intelligence.api.middleware.identity import (
    require_authenticated_identity,
)
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1/hierarchy", tags=["hierarchy"])


def _pg(settings: Optional[Settings] = None):
    s = settings or Settings()
    return psycopg2.connect(s.pg_dsn)


def _rows(conn, query: str, params=None) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(query, params or ())
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _row(conn, query: str, params=None) -> Optional[Dict[str, Any]]:
    rows = _rows(conn, query, params)
    return rows[0] if rows else None


# ── Sites ──


@router.get("/sites")
def list_sites(
    request: Request,
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    require_authenticated_identity(
        request, detail="Hierarchy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        clauses, params = [], []
        if tenant_id:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        return _rows(conn, f"SELECT * FROM sites{where} ORDER BY name LIMIT %s", params)
    finally:
        conn.close()


# ── Facilities ──


@router.get("/facilities")
def list_facilities(
    request: Request,
    site_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
):
    require_authenticated_identity(
        request, detail="Hierarchy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        return _rows(
            conn,
            "SELECT * FROM facilities WHERE site_id = %s ORDER BY name LIMIT %s",
            (site_id, limit),
        )
    finally:
        conn.close()


# ── Systems ──


@router.get("/systems")
def list_systems(
    request: Request,
    facility_id: str = Query(...),
    system_group: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    require_authenticated_identity(
        request, detail="Hierarchy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        clauses = ["facility_id = %s"]
        params: list = [facility_id]
        if system_group:
            clauses.append("system_group = %s")
            params.append(system_group)
        where = " WHERE " + " AND ".join(clauses)
        params.append(limit)
        return _rows(conn, f"SELECT * FROM systems{where} ORDER BY name LIMIT %s", params)
    finally:
        conn.close()


# ── Equipment Units ──


class EquipmentUpsertPayload(BaseModel):
    equipment_unit_id: str
    system_id: str
    tag: str
    iso_equipment_class: str
    equipment_family: Optional[str] = None
    oem_name: Optional[str] = None
    oem_model: Optional[str] = None
    criticality: Optional[str] = None
    service_medium: Optional[str] = None
    duty_type: Optional[str] = None
    safety_critical: bool = False
    install_date: Optional[str] = None
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    rated_power_kw: Optional[float] = None
    rated_speed_rpm: Optional[float] = None
    tenant_id: Optional[str] = None
    hierarchy_path: Optional[str] = None


@router.get("/equipment")
def list_equipment(
    request: Request,
    system_id: Optional[str] = Query(None),
    iso_equipment_class: Optional[str] = Query(None),
    equipment_family: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    require_authenticated_identity(
        request, detail="Hierarchy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        clauses, params = [], []
        if system_id:
            clauses.append("system_id = %s")
            params.append(system_id)
        if iso_equipment_class:
            clauses.append("iso_equipment_class = %s")
            params.append(iso_equipment_class)
        if equipment_family:
            clauses.append("equipment_family = %s")
            params.append(equipment_family)
        if tenant_id:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        return _rows(conn, f"SELECT * FROM equipment_units{where} ORDER BY tag LIMIT %s", params)
    finally:
        conn.close()


@router.get("/equipment/{equipment_unit_id}")
def get_equipment(request: Request, equipment_unit_id: str):
    require_authenticated_identity(
        request, detail="Hierarchy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        row = _row(
            conn,
            "SELECT * FROM equipment_units WHERE equipment_unit_id = %s",
            (equipment_unit_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Equipment unit not found")
        return row
    finally:
        conn.close()


@router.get("/equipment/{equipment_unit_id}/path")
def get_equipment_path(request: Request, equipment_unit_id: str):
    """Full hierarchy context L1→L6 for an equipment unit."""
    require_authenticated_identity(
        request, detail="Hierarchy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        row = _row(
            conn,
            """
            SELECT
                e.equipment_unit_id, e.tag, e.iso_equipment_class, e.equipment_family,
                e.criticality, e.service_medium, e.oem_name, e.oem_model,
                e.safety_critical, e.duty_type,
                s.system_id, s.system_type, s.system_group, s.name AS system_name,
                f.facility_id, f.facility_type, f.name AS facility_name,
                si.site_id, si.name AS site_name, si.basin_region, si.onshore_offshore,
                bu.bu_code, bu.name AS bu_name,
                ind.industry_code, ind.name AS industry_name
            FROM equipment_units e
            JOIN systems s ON e.system_id = s.system_id
            JOIN facilities f ON s.facility_id = f.facility_id
            JOIN sites si ON f.site_id = si.site_id
            JOIN business_units bu ON si.bu_code = bu.bu_code
            JOIN industries ind ON bu.industry_code = ind.industry_code
            WHERE e.equipment_unit_id = %s
            """,
            (equipment_unit_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Equipment unit not found")
        return row
    finally:
        conn.close()


@router.post("/equipment")
def upsert_equipment(request: Request, payload: EquipmentUpsertPayload):
    require_authenticated_identity(
        request, detail="Equipment upsert requires an authenticated identity"
    )
    conn = _pg()
    try:
        data = payload.model_dump()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO equipment_units (
                        equipment_unit_id, system_id, tag, iso_equipment_class,
                        equipment_family, oem_name, oem_model, criticality,
                        service_medium, duty_type, safety_critical, install_date,
                        design_pressure_bar, design_temperature_c, rated_power_kw,
                        rated_speed_rpm, tenant_id, hierarchy_path
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (equipment_unit_id) DO UPDATE SET
                        tag = EXCLUDED.tag,
                        iso_equipment_class = EXCLUDED.iso_equipment_class,
                        equipment_family = EXCLUDED.equipment_family,
                        oem_name = EXCLUDED.oem_name,
                        oem_model = EXCLUDED.oem_model,
                        criticality = EXCLUDED.criticality,
                        updated_at = now()
                    RETURNING equipment_unit_id
                    """,
                    (
                        data["equipment_unit_id"], data["system_id"], data["tag"],
                        data["iso_equipment_class"], data["equipment_family"],
                        data["oem_name"], data["oem_model"], data["criticality"],
                        data["service_medium"], data["duty_type"], data["safety_critical"],
                        data["install_date"], data["design_pressure_bar"],
                        data["design_temperature_c"], data["rated_power_kw"],
                        data["rated_speed_rpm"], data["tenant_id"], data["hierarchy_path"],
                    ),
                )
                result_id = cur.fetchone()[0]
        return {"status": "ok", "equipment_unit_id": result_id}
    finally:
        conn.close()


# ── Sub-units ──


@router.get("/subunits")
def list_subunits(
    request: Request,
    equipment_unit_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
):
    require_authenticated_identity(
        request, detail="Hierarchy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        return _rows(
            conn,
            "SELECT * FROM subunits WHERE equipment_unit_id = %s ORDER BY subunit_type_code LIMIT %s",
            (equipment_unit_id, limit),
        )
    finally:
        conn.close()


# ── Components ──


@router.get("/components")
def list_components(
    request: Request,
    subunit_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
):
    require_authenticated_identity(
        request, detail="Hierarchy queries require an authenticated identity"
    )
    conn = _pg()
    try:
        return _rows(
            conn,
            "SELECT * FROM components WHERE subunit_id = %s ORDER BY component_type_code LIMIT %s",
            (subunit_id, limit),
        )
    finally:
        conn.close()
