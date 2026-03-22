"""Maximo bidirectional ingestion adapter.

READ direction (this adapter):
  - Assets (MXASSET) → CanonicalEquipment
  - Work orders (MXWO) → CanonicalWorkOrder
  - Failure reports (MXFAILUREREPORT) → CanonicalFailureEvent

Maximo Failure Class hierarchy is mapped to ISO 14224 via maximo_failure_code_map:
  - Problem code → failure_mode_code
  - Cause code → failure_cause_code
  - Remedy code → maintenance_action_code

WRITE direction is handled by the existing cmms/maximo.py adapter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from maintenance_intelligence.ingestion.base import (
    BaseIngestionAdapter,
    CanonicalEquipment,
    CanonicalFailureEvent,
    CanonicalWorkOrder,
)
from maintenance_intelligence.ingestion.code_mapper import CodeMapper


MAXIMO_EQUIPMENT_CLASS_MAP = {
    "PUMP": "CENTRIFUGAL_PUMP",
    "COMPRESSOR": "CENTRIFUGAL_COMPRESSOR",
    "TURBINE": "GAS_TURBINE",
    "MOTOR": "MOTOR",
    "GENERATOR": "GENERATOR",
    "TRANSFORMER": "TRANSFORMER",
    "VESSEL": "PRESSURE_VESSEL",
    "EXCHANGER": "HEAT_EXCHANGER",
    "VALVE": "CONTROL_VALVE",
    "INSTRUMENT": "TRANSMITTER",
}

MAXIMO_PRIORITY_MAP = {
    1: "CRITICAL",
    2: "HIGH",
    3: "MEDIUM",
    4: "LOW",
}

MAXIMO_WO_TYPE_MAP = {
    "CM": "CORRECTIVE",
    "PM": "PREVENTIVE",
    "EM": "CORRECTIVE",
    "CP": "CONDITION_BASED",
}


class MaximoIngestionAdapter(BaseIngestionAdapter):
    """Maximo OSLC/REST ingestion adapter (read direction).

    Configuration:
      - base_url: Maximo REST endpoint (e.g. https://maximo.example.com/maximo/oslc)
      - api_key: Maximo API key
      - site_id: Maximo site to filter
    """

    source_system = "MAXIMO"
    adapter_name = "maximo_ingest"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        site_id: str = "BEDFORD",
        tenant_id: Optional[str] = None,
        timeout_s: int = 15,
        code_mapper: Optional[CodeMapper] = None,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.site_id = site_id
        self.tenant_id = tenant_id
        self.timeout_s = timeout_s
        self._mapper = code_mapper or CodeMapper()

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            h["apikey"] = self.api_key
        return h

    def test_connection(self) -> Dict[str, Any]:
        if not self.base_url:
            return {"status": "not_configured", "adapter": self.adapter_name}
        try:
            resp = httpx.get(
                f"{self.base_url}/os/mxasset?oslc.pageSize=1&oslc.where=siteid=%22{self.site_id}%22",
                headers=self._headers(),
                timeout=self.timeout_s,
            )
            return {
                "status": "ok" if resp.status_code == 200 else "error",
                "adapter": self.adapter_name,
                "http_status": resp.status_code,
            }
        except Exception as e:
            return {"status": "error", "adapter": self.adapter_name, "error": str(e)}

    def normalize_asset(self, record: Dict[str, Any]) -> CanonicalEquipment:
        """Normalize a Maximo MXASSET record."""
        asset_num = str(record.get("assetnum", ""))
        asset_type = str(record.get("assettype", "")).upper()
        iso_class = MAXIMO_EQUIPMENT_CLASS_MAP.get(asset_type, asset_type)

        return CanonicalEquipment(
            equipment_unit_id=f"MX-{asset_num}",
            tag=record.get("location", asset_num),
            iso_equipment_class=iso_class,
            oem_name=record.get("vendor"),
            oem_model=record.get("modelnum"),
            criticality=str(record.get("priority", "")).upper() or None,
            install_date=record.get("installdate"),
            tenant_id=self.tenant_id,
            raw_source={"source_system": "MAXIMO", "assetnum": asset_num, "siteid": self.site_id},
        )

    def normalize_work_order(self, record: Dict[str, Any]) -> CanonicalWorkOrder:
        """Normalize a Maximo MXWO record."""
        wo_num = str(record.get("wonum", ""))
        asset_num = str(record.get("assetnum", ""))
        wo_type = str(record.get("worktype", "")).upper()
        priority = record.get("wopriority", record.get("priority"))

        return CanonicalWorkOrder(
            wo_id=f"MX-WO-{wo_num}",
            source_system="MAXIMO",
            equipment_unit_id=f"MX-{asset_num}" if asset_num else None,
            asset_id=record.get("location", asset_num),
            tenant_id=self.tenant_id,
            maintenance_type=MAXIMO_WO_TYPE_MAP.get(wo_type, "CORRECTIVE"),
            status=_normalize_maximo_status(record.get("status")),
            title=record.get("description", ""),
            description=record.get("description_longdescription"),
            priority=MAXIMO_PRIORITY_MAP.get(priority, "MEDIUM") if isinstance(priority, int) else str(priority or "MEDIUM"),
            planned_start_ts=_parse_maximo_ts(record.get("schedstart")),
            actual_start_ts=_parse_maximo_ts(record.get("actstart")),
            completion_ts=_parse_maximo_ts(record.get("actfinish")),
            labour_hours=record.get("actlabhrs"),
            raw_source_ids={"wonum": wo_num, "siteid": self.site_id},
        )

    def normalize_failure_report(self, record: Dict[str, Any]) -> CanonicalFailureEvent:
        """Normalize a Maximo failure report to a canonical failure event.

        Maps Maximo Failure Class hierarchy via maximo_failure_code_map:
          - Problem code → failure_mode_code
          - Cause code → failure_cause_code
          - Remedy code → maintenance_action_code
        """
        wo_num = str(record.get("wonum", ""))
        asset_num = str(record.get("assetnum", ""))
        problem = str(record.get("failurecode", record.get("problem", ""))).strip()
        cause = str(record.get("cause", "")).strip()
        remedy = str(record.get("remedy", "")).strip()

        failure_mode = self._mapper.map_maximo_code("PROBLEM", problem) if problem else None
        failure_cause = self._mapper.map_maximo_code("CAUSE", cause) if cause else None
        maint_action = self._mapper.map_maximo_code("REMEDY", remedy) if remedy else None

        return CanonicalFailureEvent(
            event_id=f"MX-FAIL-{wo_num}-{problem or 'UNK'}",
            source_system="MAXIMO",
            equipment_unit_id=f"MX-{asset_num}" if asset_num else None,
            asset_id=record.get("location", asset_num),
            tenant_id=self.tenant_id,
            failure_mode_code=failure_mode,
            failure_cause_code=failure_cause,
            maintenance_action_code=maint_action,
            severity=MAXIMO_PRIORITY_MAP.get(record.get("wopriority"), None),
            kind="alarm",
            summary=record.get("description", ""),
            details={
                "maximo_problem": problem,
                "maximo_cause": cause,
                "maximo_remedy": remedy,
                "maximo_failurecode": record.get("failurecode"),
            },
            lineage={"source": "maximo_ingest", "wonum": wo_num},
            raw_source_ids={"wonum": wo_num, "siteid": self.site_id},
            failure_start_ts=_parse_maximo_ts(record.get("reportdate", record.get("actstart"))),
            restoration_ts=_parse_maximo_ts(record.get("actfinish")),
        )

    def fetch_equipment(self, *, records: Optional[List[Dict]] = None, **kwargs) -> List[CanonicalEquipment]:
        if records:
            return [self.normalize_asset(r) for r in records]
        return []

    def fetch_failure_events(self, *, records: Optional[List[Dict]] = None, **kwargs) -> List[CanonicalFailureEvent]:
        if records:
            return [self.normalize_failure_report(r) for r in records]
        return []

    def fetch_work_orders(self, *, records: Optional[List[Dict]] = None, **kwargs) -> List[CanonicalWorkOrder]:
        if records:
            return [self.normalize_work_order(r) for r in records]
        return []


def _parse_maximo_ts(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _normalize_maximo_status(status) -> str:
    s = str(status or "").upper()
    if s in ("COMP", "CLOSE"):
        return "COMPLETE"
    if s in ("INPRG", "WMATL"):
        return "IN_PROGRESS"
    if s in ("WAPPR", "WSCH"):
        return "PLANNED"
    return "PENDING"
