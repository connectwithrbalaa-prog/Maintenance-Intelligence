"""Repository functions for the ISO 14224 asset hierarchy (L3–L8).

All functions accept a psycopg2 connection and return dicts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def list_sites(conn, *, tenant_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM sites"
    params: Dict[str, Any] = {"limit": limit}
    if tenant_id:
        query += " WHERE tenant_id = %(tenant_id)s"
        params["tenant_id"] = tenant_id
    query += " ORDER BY name LIMIT %(limit)s"
    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_equipment_unit(conn, equipment_unit_id: str) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM equipment_units WHERE equipment_unit_id = %s",
            (equipment_unit_id,),
        )
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None


def list_equipment_units(
    conn,
    *,
    system_id: Optional[str] = None,
    iso_equipment_class: Optional[str] = None,
    equipment_family: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    clauses = []
    params: Dict[str, Any] = {"limit": limit}
    if system_id:
        clauses.append("system_id = %(system_id)s")
        params["system_id"] = system_id
    if iso_equipment_class:
        clauses.append("iso_equipment_class = %(iso_equipment_class)s")
        params["iso_equipment_class"] = iso_equipment_class
    if equipment_family:
        clauses.append("equipment_family = %(equipment_family)s")
        params["equipment_family"] = equipment_family
    if tenant_id:
        clauses.append("tenant_id = %(tenant_id)s")
        params["tenant_id"] = tenant_id
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM equipment_units{where} ORDER BY tag LIMIT %(limit)s", params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_hierarchy_path(conn, equipment_unit_id: str) -> Dict[str, Any]:
    """Return the full hierarchy context for an equipment unit (L3→L6)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                e.equipment_unit_id, e.tag, e.iso_equipment_class, e.equipment_family,
                e.criticality, e.service_medium, e.oem_name, e.oem_model,
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
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else {}


def upsert_equipment_unit(conn, data: Dict[str, Any]) -> str:
    """Insert or update an equipment unit. Returns equipment_unit_id."""
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
                    %(equipment_unit_id)s, %(system_id)s, %(tag)s, %(iso_equipment_class)s,
                    %(equipment_family)s, %(oem_name)s, %(oem_model)s, %(criticality)s,
                    %(service_medium)s, %(duty_type)s, %(safety_critical)s, %(install_date)s,
                    %(design_pressure_bar)s, %(design_temperature_c)s, %(rated_power_kw)s,
                    %(rated_speed_rpm)s, %(tenant_id)s, %(hierarchy_path)s
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
                {
                    "equipment_unit_id": data.get("equipment_unit_id"),
                    "system_id": data.get("system_id"),
                    "tag": data.get("tag"),
                    "iso_equipment_class": data.get("iso_equipment_class"),
                    "equipment_family": data.get("equipment_family"),
                    "oem_name": data.get("oem_name"),
                    "oem_model": data.get("oem_model"),
                    "criticality": data.get("criticality"),
                    "service_medium": data.get("service_medium"),
                    "duty_type": data.get("duty_type"),
                    "safety_critical": data.get("safety_critical", False),
                    "install_date": data.get("install_date"),
                    "design_pressure_bar": data.get("design_pressure_bar"),
                    "design_temperature_c": data.get("design_temperature_c"),
                    "rated_power_kw": data.get("rated_power_kw"),
                    "rated_speed_rpm": data.get("rated_speed_rpm"),
                    "tenant_id": data.get("tenant_id"),
                    "hierarchy_path": data.get("hierarchy_path"),
                },
            )
            return cur.fetchone()[0]
