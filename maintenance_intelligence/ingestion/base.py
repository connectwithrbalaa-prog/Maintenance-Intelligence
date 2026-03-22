"""Base ingestion adapter interface.

All source-specific adapters (SAP PM, Maximo, SCADA) implement this
contract so the ingestion pipeline treats them uniformly.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class CanonicalEquipment:
    """Equipment record normalized to the ISO 14224 canonical schema."""

    equipment_unit_id: str
    tag: str
    iso_equipment_class: str
    system_id: Optional[str] = None
    equipment_family: Optional[str] = None
    oem_name: Optional[str] = None
    oem_model: Optional[str] = None
    criticality: Optional[str] = None
    service_medium: Optional[str] = None
    duty_type: Optional[str] = None
    safety_critical: bool = False
    install_date: Optional[str] = None
    tenant_id: Optional[str] = None
    hierarchy_path: Optional[str] = None
    raw_source: Optional[Dict[str, Any]] = None


@dataclass
class CanonicalFailureEvent:
    """Failure event normalized to the ISO 14224 canonical schema."""

    event_id: str
    source_system: str
    equipment_unit_id: Optional[str] = None
    component_id: Optional[str] = None
    asset_id: Optional[str] = None
    tenant_id: Optional[str] = None
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
    failure_start_ts: Optional[datetime] = None
    restoration_ts: Optional[datetime] = None
    downtime_hours: Optional[float] = None


@dataclass
class CanonicalWorkOrder:
    """Work order normalized to the canonical schema."""

    wo_id: str
    source_system: str
    equipment_unit_id: Optional[str] = None
    asset_id: Optional[str] = None
    tenant_id: Optional[str] = None
    maintenance_type: Optional[str] = None
    maintenance_action_code: Optional[str] = None
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    planned_start_ts: Optional[datetime] = None
    actual_start_ts: Optional[datetime] = None
    completion_ts: Optional[datetime] = None
    labour_hours: Optional[float] = None
    parts_cost: Optional[float] = None
    related_failure_event_id: Optional[str] = None
    raw_source_ids: Optional[Dict[str, Any]] = None


@dataclass
class CanonicalSignal:
    """Time-series signal point normalized to the canonical schema."""

    signal_id: str
    source_system: str
    equipment_unit_id: Optional[str] = None
    component_id: Optional[str] = None
    asset_id: Optional[str] = None
    signal_type: str = ""
    value: Optional[float] = None
    unit: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class IngestionResult:
    """Summary of an ingestion batch run."""

    source_system: str
    adapter_name: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    equipment_count: int = 0
    failure_event_count: int = 0
    work_order_count: int = 0
    signal_count: int = 0
    error_count: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.error_count == 0


class BaseIngestionAdapter(abc.ABC):
    """Abstract base for all ingestion adapters.

    Each adapter must implement:
      - fetch_equipment() → list of CanonicalEquipment
      - fetch_failure_events() → list of CanonicalFailureEvent
      - fetch_work_orders() → list of CanonicalWorkOrder

    SCADA adapters additionally implement:
      - fetch_signals() → list of CanonicalSignal
    """

    source_system: str = "UNKNOWN"
    adapter_name: str = "base"

    @abc.abstractmethod
    def fetch_equipment(self, **kwargs) -> List[CanonicalEquipment]:
        """Pull equipment master data and normalize to canonical schema."""
        ...

    @abc.abstractmethod
    def fetch_failure_events(self, **kwargs) -> List[CanonicalFailureEvent]:
        """Pull failure/notification records and normalize with ISO codes."""
        ...

    @abc.abstractmethod
    def fetch_work_orders(self, **kwargs) -> List[CanonicalWorkOrder]:
        """Pull work orders and normalize to canonical schema."""
        ...

    def fetch_signals(self, **kwargs) -> List[CanonicalSignal]:
        """Pull time-series signals (override in SCADA adapters)."""
        return []

    def test_connection(self) -> Dict[str, Any]:
        """Verify connectivity to the source system."""
        return {"status": "not_implemented", "adapter": self.adapter_name}
