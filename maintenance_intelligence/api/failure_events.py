"""API router for canonical failure events (ISO 14224 §9).

Endpoints:
  GET  /api/v1/failure-events           — list failure events (filterable)
  GET  /api/v1/failure-events/{event_id} — get single failure event
  POST /api/v1/failure-events           — create canonical failure event
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from maintenance_intelligence.api.middleware.identity import (
    require_authenticated_identity,
    get_identity,
    get_identity_subject,
    get_identity_org_id,
)
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1/failure-events", tags=["failure-events"])


def _pg(settings: Optional[Settings] = None):
    s = settings or Settings()
    return psycopg2.connect(s.pg_dsn)


def _rows(conn, query: str, params=None) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(query, params or ())
        cols = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            for k, v in d.items():
                if isinstance(v, datetime):
                    d[k] = v.isoformat()
            rows.append(d)
        return rows


def _row(conn, query: str, params=None) -> Optional[Dict[str, Any]]:
    rows = _rows(conn, query, params)
    return rows[0] if rows else None


class FailureEventPayload(BaseModel):
    event_id: Optional[str] = None
    tenant_id: Optional[str] = None
    source_system: str = Field(..., description="SAP, MAXIMO, SCADA, MANUAL, SIMULATOR")
    equipment_unit_id: Optional[str] = None
    component_id: Optional[str] = None
    asset_id: Optional[str] = None
    failure_mode_code: Optional[str] = None
    failure_mechanism_code: Optional[str] = None
    failure_cause_code: Optional[str] = None
    maintenance_action_code: Optional[str] = None
    detection_method_code: Optional[str] = None
    consequence_code: Optional[str] = None
    impact_level: Optional[str] = None
    severity: Optional[str] = None
    kind: Optional[str] = None
    summary: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    lineage: Optional[Dict[str, Any]] = None
    raw_source_ids: Optional[Dict[str, Any]] = None
    failure_start_ts: Optional[str] = None
    restoration_ts: Optional[str] = None
    downtime_hours: Optional[float] = None


@router.get("")
def list_failure_events(
    request: Request,
    equipment_unit_id: Optional[str] = Query(None),
    component_id: Optional[str] = Query(None),
    asset_id: Optional[str] = Query(None),
    failure_mode_code: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    source_system: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    identity = require_authenticated_identity(
        request, detail="Failure event queries require an authenticated identity"
    )
    actor_org_id = get_identity_org_id(identity)
    # Enforce tenant isolation: if the authenticated identity carries an org_id,
    # the query may not cross into a different tenant's data.
    if actor_org_id and tenant_id and tenant_id != actor_org_id:
        raise HTTPException(
            status_code=403,
            detail="Cross-tenant access is not permitted",
        )
    # Automatically scope the query to the actor's org when no explicit
    # tenant_id filter was supplied by the caller.
    if actor_org_id and not tenant_id:
        tenant_id = actor_org_id
    conn = _pg()
    try:
        clauses, params = [], []
        if equipment_unit_id:
            clauses.append("equipment_unit_id = %s")
            params.append(equipment_unit_id)
        if component_id:
            clauses.append("component_id = %s")
            params.append(component_id)
        if asset_id:
            clauses.append("asset_id = %s")
            params.append(asset_id)
        if failure_mode_code:
            clauses.append("failure_mode_code = %s")
            params.append(failure_mode_code.upper())
        if tenant_id:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if source_system:
            clauses.append("source_system = %s")
            params.append(source_system.upper())
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        return _rows(
            conn,
            f"SELECT * FROM failure_events{where} ORDER BY failure_start_ts DESC NULLS LAST, created_at DESC LIMIT %s",
            params,
        )
    finally:
        conn.close()


@router.get("/{event_id}")
def get_failure_event(request: Request, event_id: str):
    require_authenticated_identity(
        request, detail="Failure event queries require an authenticated identity"
    )
    conn = _pg()
    try:
        row = _row(conn, "SELECT * FROM failure_events WHERE event_id = %s", (event_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Failure event not found")
        return row
    finally:
        conn.close()


@router.post("")
def create_failure_event(request: Request, payload: FailureEventPayload):
    identity = require_authenticated_identity(
        request, detail="Creating failure events requires an authenticated identity"
    )
    actor_org_id = get_identity_org_id(identity)
    # Block cross-tenant writes: if identity has an org_id, payload tenant_id
    # must match (or be absent, in which case it inherits from the identity).
    if actor_org_id and payload.tenant_id and payload.tenant_id != actor_org_id:
        raise HTTPException(
            status_code=403,
            detail="Cross-tenant write is not permitted",
        )
    if actor_org_id and not payload.tenant_id:
        payload = payload.model_copy(update={"tenant_id": actor_org_id})
    conn = _pg()
    try:
        event_id = payload.event_id or f"FE-{uuid.uuid4().hex[:12]}"
        data = payload.model_dump()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO failure_events (
                        event_id, tenant_id, source_system, equipment_unit_id,
                        component_id, asset_id, failure_mode_code, failure_mechanism_code,
                        failure_cause_code, maintenance_action_code, detection_method_code,
                        consequence_code, impact_level, severity, kind, summary,
                        details, lineage, raw_source_ids,
                        failure_start_ts, restoration_ts, downtime_hours
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s
                    )
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """,
                    (
                        event_id, data.get("tenant_id"), data["source_system"],
                        data.get("equipment_unit_id"), data.get("component_id"),
                        data.get("asset_id"), data.get("failure_mode_code"),
                        data.get("failure_mechanism_code"), data.get("failure_cause_code"),
                        data.get("maintenance_action_code"), data.get("detection_method_code"),
                        data.get("consequence_code"), data.get("impact_level"),
                        data.get("severity"), data.get("kind"), data.get("summary"),
                        json.dumps(data.get("details")) if data.get("details") else None,
                        json.dumps(data.get("lineage")) if data.get("lineage") else None,
                        json.dumps(data.get("raw_source_ids")) if data.get("raw_source_ids") else None,
                        data.get("failure_start_ts"), data.get("restoration_ts"),
                        data.get("downtime_hours"),
                    ),
                )
                result = cur.fetchone()
        return {
            "status": "ok",
            "event_id": event_id,
            "created": result is not None,
            "recorded_by": get_identity_subject(identity),
        }
    finally:
        conn.close()
