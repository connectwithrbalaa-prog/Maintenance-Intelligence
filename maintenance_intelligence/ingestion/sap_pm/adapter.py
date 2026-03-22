"""SAP PM ingestion adapter.

Maps SAP PM data structures to the ISO 14224 canonical model:
  - Equipment master (EQUI/IFLOT) → CanonicalEquipment
  - Notifications (IW21/IW28, QMEL) → CanonicalFailureEvent
  - Maintenance orders (IW31/IW38) → CanonicalWorkOrder

SAP PM catalogs are mapped to ISO 14224 via sap_failure_code_map:
  - Object Part catalog → failure_mode_code
  - Damage catalog → failure_mechanism_code
  - Cause catalog → failure_cause_code
  - Activity catalog → maintenance_action_code
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from maintenance_intelligence.ingestion.base import (
    BaseIngestionAdapter,
    CanonicalEquipment,
    CanonicalFailureEvent,
    CanonicalWorkOrder,
)
from maintenance_intelligence.ingestion.code_mapper import CodeMapper


SAP_ORDER_TYPE_MAP = {
    "PM01": "CORRECTIVE",
    "PM02": "PREVENTIVE",
    "PM03": "CONDITION_BASED",
    "PM04": "DETECTIVE",
    "PM05": "CORRECTIVE",
    "PM06": "PREVENTIVE",
    "PM10": "CORRECTIVE",
}

SAP_PRIORITY_MAP = {
    "1": "CRITICAL",
    "2": "HIGH",
    "3": "MEDIUM",
    "4": "LOW",
}

SAP_EQUIPMENT_CLASS_MAP = {
    "PUMP": "CENTRIFUGAL_PUMP",
    "CENT_PUMP": "CENTRIFUGAL_PUMP",
    "RECIP_COMP": "RECIP_COMPRESSOR",
    "CENT_COMP": "CENTRIFUGAL_COMPRESSOR",
    "GAS_TURB": "GAS_TURBINE",
    "STM_TURB": "STEAM_TURBINE",
    "MOTOR": "MOTOR",
    "GENERATOR": "GENERATOR",
    "TRANSFORMER": "TRANSFORMER",
    "VESSEL": "PRESSURE_VESSEL",
    "HX": "HEAT_EXCHANGER",
    "COLUMN": "COLUMN",
    "TANK": "TANK",
    "CTRL_VALVE": "CONTROL_VALVE",
    "ONOFF_VALVE": "ONOFF_VALVE",
    "XMTR": "TRANSMITTER",
    "ESD": "ESD_SYSTEM",
    "FGS": "FIRE_GAS_SYSTEM",
    "RV": "RELIEF_VALVE",
}


class SAPPMAdapter(BaseIngestionAdapter):
    """SAP PM ingestion adapter.

    Configuration:
      - base_url: SAP OData endpoint or RFC gateway URL
      - client: SAP client number
      - api_key: API key or OAuth token
      - plant: SAP plant code to filter

    In production, this adapter calls SAP OData/BAPI endpoints.
    The current implementation accepts pre-fetched record dicts
    for normalization, enabling both live integration and batch import.
    """

    source_system = "SAP"
    adapter_name = "sap_pm"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        client: Optional[str] = None,
        api_key: Optional[str] = None,
        plant: Optional[str] = None,
        tenant_id: Optional[str] = None,
        code_mapper: Optional[CodeMapper] = None,
    ):
        self.base_url = base_url
        self.client = client
        self.api_key = api_key
        self.plant = plant
        self.tenant_id = tenant_id
        self._mapper = code_mapper or CodeMapper()

    def test_connection(self) -> Dict[str, Any]:
        if not self.base_url:
            return {"status": "not_configured", "adapter": self.adapter_name}
        return {
            "status": "configured",
            "adapter": self.adapter_name,
            "base_url": self.base_url,
            "plant": self.plant,
        }

    def normalize_equipment(self, record: Dict[str, Any]) -> CanonicalEquipment:
        """Normalize a single SAP equipment master record."""
        equi_id = str(record.get("EQUNR", record.get("equipment_number", "")))
        tag = str(record.get("TPLNR", record.get("functional_location", equi_id)))
        sap_class = str(record.get("EQART", record.get("equipment_category", ""))).upper()
        iso_class = SAP_EQUIPMENT_CLASS_MAP.get(sap_class, sap_class)

        return CanonicalEquipment(
            equipment_unit_id=f"SAP-{equi_id}",
            tag=tag,
            iso_equipment_class=iso_class,
            oem_name=record.get("HERST", record.get("manufacturer")),
            oem_model=record.get("TYPBZ", record.get("model_number")),
            criticality=record.get("criticality"),
            service_medium=record.get("service_medium"),
            install_date=record.get("INBDT", record.get("start_up_date")),
            tenant_id=self.tenant_id,
            raw_source={"source_system": "SAP", "EQUNR": equi_id, "TPLNR": tag},
        )

    def normalize_notification(self, record: Dict[str, Any]) -> CanonicalFailureEvent:
        """Normalize a SAP PM notification (QMEL) to a canonical failure event.

        Maps SAP PM catalogs via sap_failure_code_map:
          - OTGRP/OTEIL (Object Part) → failure_mode_code
          - FEGRP/FECOD (Damage) → failure_mechanism_code
          - URGRP/URCOD (Cause) → failure_cause_code
        """
        notif_id = str(record.get("QMNUM", record.get("notification_number", "")))
        equi_id = str(record.get("EQUNR", record.get("equipment_number", "")))
        funct_loc = str(record.get("TPLNR", record.get("functional_location", "")))

        damage_code = str(record.get("FECOD", record.get("damage_code", ""))).strip()
        cause_code = str(record.get("URCOD", record.get("cause_code", ""))).strip()
        object_part = str(record.get("OTEIL", record.get("object_part_code", ""))).strip()

        failure_mode = self._mapper.map_sap_code("OBJECT_PART", object_part) if object_part else None
        failure_mechanism = self._mapper.map_sap_code("DAMAGE", damage_code) if damage_code else None
        failure_cause = self._mapper.map_sap_code("CAUSE", cause_code) if cause_code else None

        start_ts = _parse_sap_datetime(record.get("AUSVN", record.get("breakdown_start")))
        end_ts = _parse_sap_datetime(record.get("AUSBS", record.get("breakdown_end")))
        downtime = None
        if start_ts and end_ts:
            downtime = round((end_ts - start_ts).total_seconds() / 3600, 2)

        priority = str(record.get("PRIOK", record.get("priority", ""))).strip()

        return CanonicalFailureEvent(
            event_id=f"SAP-NOTIF-{notif_id}",
            source_system="SAP",
            equipment_unit_id=f"SAP-{equi_id}" if equi_id else None,
            asset_id=funct_loc or equi_id or None,
            tenant_id=self.tenant_id,
            failure_mode_code=failure_mode,
            failure_mechanism_code=failure_mechanism,
            failure_cause_code=failure_cause,
            detection_method_code=_sap_detection_method(record),
            severity=SAP_PRIORITY_MAP.get(priority, priority or None),
            kind="alarm",
            summary=record.get("QMTXT", record.get("notification_text", "")),
            details={
                "sap_notification_type": record.get("QMART"),
                "sap_damage_code": damage_code,
                "sap_cause_code": cause_code,
                "sap_object_part": object_part,
            },
            lineage={"source": "sap_pm", "notification": notif_id},
            raw_source_ids={"notification_id": notif_id},
            failure_start_ts=start_ts,
            restoration_ts=end_ts,
            downtime_hours=downtime,
        )

    def normalize_order(self, record: Dict[str, Any]) -> CanonicalWorkOrder:
        """Normalize a SAP PM maintenance order to a canonical work order."""
        order_id = str(record.get("AUFNR", record.get("order_number", "")))
        equi_id = str(record.get("EQUNR", record.get("equipment_number", "")))
        order_type = str(record.get("AUART", record.get("order_type", ""))).upper()
        priority = str(record.get("PRIOK", record.get("priority", ""))).strip()

        activity_code = str(record.get("activity_code", "")).strip()
        maint_action = self._mapper.map_sap_code("ACTIVITY", activity_code) if activity_code else None

        return CanonicalWorkOrder(
            wo_id=f"SAP-ORDER-{order_id}",
            source_system="SAP",
            equipment_unit_id=f"SAP-{equi_id}" if equi_id else None,
            asset_id=record.get("TPLNR", record.get("functional_location")),
            tenant_id=self.tenant_id,
            maintenance_type=SAP_ORDER_TYPE_MAP.get(order_type, "CORRECTIVE"),
            maintenance_action_code=maint_action,
            status=_sap_order_status(record),
            title=record.get("KTEXT", record.get("order_description", "")),
            description=record.get("LTXA1", record.get("long_text")),
            priority=SAP_PRIORITY_MAP.get(priority, priority or "MEDIUM"),
            planned_start_ts=_parse_sap_datetime(record.get("GSTRP", record.get("planned_start"))),
            actual_start_ts=_parse_sap_datetime(record.get("GETRI", record.get("actual_start"))),
            completion_ts=_parse_sap_datetime(record.get("IDAT2", record.get("completion_date"))),
            related_failure_event_id=record.get("QMNUM"),
            raw_source_ids={"order_id": order_id, "notification_id": record.get("QMNUM")},
        )

    def fetch_equipment(self, *, records: Optional[List[Dict]] = None, **kwargs) -> List[CanonicalEquipment]:
        if records:
            return [self.normalize_equipment(r) for r in records]
        return []

    def fetch_failure_events(self, *, records: Optional[List[Dict]] = None, **kwargs) -> List[CanonicalFailureEvent]:
        if records:
            return [self.normalize_notification(r) for r in records]
        return []

    def fetch_work_orders(self, *, records: Optional[List[Dict]] = None, **kwargs) -> List[CanonicalWorkOrder]:
        if records:
            return [self.normalize_order(r) for r in records]
        return []


def _parse_sap_datetime(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _sap_order_status(record: Dict[str, Any]) -> str:
    status = str(record.get("STAT", record.get("system_status", ""))).upper()
    if "TECO" in status or "CLSD" in status:
        return "COMPLETE"
    if "REL" in status:
        return "IN_PROGRESS"
    if "CRTD" in status:
        return "PLANNED"
    return "PENDING"


def _sap_detection_method(record: Dict[str, Any]) -> Optional[str]:
    notif_type = str(record.get("QMART", "")).upper()
    if notif_type in ("M1", "M2"):
        return "PER"
    if notif_type in ("M3",):
        return "MON"
    return None
