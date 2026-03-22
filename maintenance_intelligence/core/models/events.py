"""Canonical failure and maintenance event models (ISO 14224 §9).

These replace the flat event structure with structured ISO 14224–aligned
failure classification fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FailureEvent(BaseModel):
    """Canonical failure event (ISO 14224 §9.2, §9.3).

    Combines equipment reference, ISO-coded failure classification,
    and downtime tracking in a single record.
    """

    event_id: str
    tenant_id: Optional[str] = None
    source_system: str = Field(
        ..., description="SAP, MAXIMO, SCADA, MANUAL, SIMULATOR"
    )
    equipment_unit_id: Optional[str] = None
    component_id: Optional[str] = Field(
        None, description="L8 component if failure is localized; nullable but preferred"
    )
    asset_id: Optional[str] = Field(
        None, description="Legacy flat asset reference for backward compatibility"
    )

    failure_mode_code: Optional[str] = Field(
        None, description="ISO 14224 failure mode: VIB, ELP, FTS, etc."
    )
    failure_mechanism_code: Optional[str] = Field(
        None, description="ISO 14224 failure mechanism: WEA, COR, FAT, etc."
    )
    failure_cause_code: Optional[str] = Field(
        None, description="ISO 14224 failure cause: DES, OPC, MNT, etc."
    )
    maintenance_action_code: Optional[str] = Field(
        None, description="ISO 14224 maintenance action: REP, RPL, OVH, etc."
    )
    detection_method_code: Optional[str] = Field(
        None, description="ISO 14224 detection method: MON, INS, PRD, etc."
    )
    consequence_code: Optional[str] = Field(
        None, description="PRODUCTION_LOSS, SAFETY, ENVIRONMENTAL, NONE"
    )
    impact_level: Optional[str] = Field(
        None, description="CRITICAL, MAJOR, MINOR, INSIGNIFICANT"
    )

    failure_start_ts: Optional[datetime] = None
    restoration_ts: Optional[datetime] = None
    downtime_hours: Optional[float] = None

    severity: Optional[str] = None
    kind: Optional[str] = Field(None, description="alarm, anomaly, measurement (legacy)")
    summary: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    lineage: Optional[Dict[str, Any]] = None

    raw_source_ids: Optional[Dict[str, Any]] = Field(
        None,
        description="Traceability: {notification_id, order_id, wo_id, scada_alarm_ids}",
    )

    created_at: Optional[datetime] = None


class MaintenanceEvent(BaseModel):
    """Canonical maintenance (preventive/corrective) event record.

    Tracks planned and unplanned maintenance activities linked to
    equipment and optionally to a triggering failure event.
    """

    event_id: str
    tenant_id: Optional[str] = None
    source_system: str
    equipment_unit_id: Optional[str] = None
    component_id: Optional[str] = None
    asset_id: Optional[str] = None

    related_failure_event_id: Optional[str] = None
    maintenance_type: str = Field(
        ..., description="CORRECTIVE, PREVENTIVE, CONDITION_BASED, DETECTIVE"
    )
    maintenance_action_code: Optional[str] = None
    work_order_id: Optional[str] = None

    planned_start_ts: Optional[datetime] = None
    actual_start_ts: Optional[datetime] = None
    completion_ts: Optional[datetime] = None
    labour_hours: Optional[float] = None
    parts_cost: Optional[float] = None

    summary: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    raw_source_ids: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
