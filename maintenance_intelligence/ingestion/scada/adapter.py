"""SCADA/historian ingestion adapter.

Reads time-series measurement points from SCADA, DCS, or historian systems
and maps them to canonical signals linked to equipment via tag mapping.

Tag mapping is configuration-driven, not hardcoded:
  - Each SCADA tag maps to an equipment_unit_id and signal_type
  - Mappings are stored in the scada_tag_map table or provided as config

Supported historian protocols (future):
  - OPC-UA: Industrial standard for real-time data
  - OPC-HDA: Historical data access
  - OSIsoft PI Web API: PI historian REST interface
  - Modbus TCP: PLC/RTU direct read
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from maintenance_intelligence.ingestion.base import (
    BaseIngestionAdapter,
    CanonicalEquipment,
    CanonicalFailureEvent,
    CanonicalSignal,
    CanonicalWorkOrder,
)


SIGNAL_TYPE_MAP = {
    "VIB": "vibration",
    "VIBRATION": "vibration",
    "VIB_RMS": "vibration",
    "TEMP": "temperature",
    "TEMPERATURE": "temperature",
    "PRESS": "pressure",
    "PRESSURE": "pressure",
    "FLOW": "flow",
    "LEVEL": "level",
    "SPEED": "speed",
    "RPM": "speed",
    "CURRENT": "current",
    "VOLTAGE": "voltage",
    "POWER": "power",
    "TORQUE": "torque",
}

UNIT_MAP = {
    "vibration": "mm/s",
    "temperature": "°C",
    "pressure": "bar",
    "flow": "m³/h",
    "level": "%",
    "speed": "rpm",
    "current": "A",
    "voltage": "V",
    "power": "kW",
    "torque": "Nm",
}


class TagMapping:
    """Configuration-driven SCADA tag to equipment mapping.

    Each tag maps a SCADA point ID to:
      - equipment_unit_id (canonical L6 reference)
      - component_id (optional L8 reference)
      - signal_type (vibration, temperature, pressure, etc.)
      - unit (mm/s, °C, bar, etc.)

    Tag mappings can be loaded from:
      - Python dict/config
      - Database table (scada_tag_map, future)
      - CSV/JSON file
    """

    def __init__(self, mappings: Optional[Dict[str, Dict[str, str]]] = None):
        self._mappings: Dict[str, Dict[str, str]] = mappings or {}

    def add(
        self,
        scada_tag: str,
        equipment_unit_id: str,
        signal_type: str,
        *,
        component_id: Optional[str] = None,
        unit: Optional[str] = None,
        asset_id: Optional[str] = None,
    ):
        normalized_type = SIGNAL_TYPE_MAP.get(signal_type.upper(), signal_type.lower())
        self._mappings[scada_tag] = {
            "equipment_unit_id": equipment_unit_id,
            "component_id": component_id or "",
            "signal_type": normalized_type,
            "unit": unit or UNIT_MAP.get(normalized_type, ""),
            "asset_id": asset_id or equipment_unit_id,
        }

    def resolve(self, scada_tag: str) -> Optional[Dict[str, str]]:
        return self._mappings.get(scada_tag)

    @property
    def tag_count(self) -> int:
        return len(self._mappings)


class SCADAAdapter(BaseIngestionAdapter):
    """SCADA/historian ingestion adapter.

    Accepts raw time-series readings as dicts and normalizes them
    to CanonicalSignal using the tag mapping configuration.

    Configuration:
      - tag_mapping: TagMapping instance with SCADA tag → equipment mapping
      - historian_url: Historian REST endpoint (future, for live polling)
      - tenant_id: Tenant scope
    """

    source_system = "SCADA"
    adapter_name = "scada"

    def __init__(
        self,
        *,
        tag_mapping: Optional[TagMapping] = None,
        historian_url: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        self.tag_mapping = tag_mapping or TagMapping()
        self.historian_url = historian_url
        self.tenant_id = tenant_id

    def test_connection(self) -> Dict[str, Any]:
        return {
            "status": "configured" if self.tag_mapping.tag_count > 0 else "no_tags",
            "adapter": self.adapter_name,
            "mapped_tags": self.tag_mapping.tag_count,
            "historian_url": self.historian_url,
        }

    def normalize_reading(self, reading: Dict[str, Any]) -> Optional[CanonicalSignal]:
        """Normalize a single SCADA time-series reading.

        Expected reading format:
          {"tag": "CT301A_VIB_DE", "value": 9.4, "timestamp": "2026-03-21T10:30:00Z", "quality": "GOOD"}
        """
        tag = str(reading.get("tag", reading.get("point_id", "")))
        mapping = self.tag_mapping.resolve(tag)
        if not mapping:
            return None

        ts = reading.get("timestamp")
        if isinstance(ts, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    ts = datetime.strptime(ts, fmt)
                    break
                except ValueError:
                    continue

        return CanonicalSignal(
            signal_id=f"SCADA-{tag}-{uuid.uuid4().hex[:8]}",
            source_system="SCADA",
            equipment_unit_id=mapping["equipment_unit_id"],
            component_id=mapping.get("component_id") or None,
            asset_id=mapping.get("asset_id"),
            signal_type=mapping["signal_type"],
            value=reading.get("value"),
            unit=mapping.get("unit", ""),
            timestamp=ts if isinstance(ts, datetime) else None,
            metadata={
                "scada_tag": tag,
                "quality": reading.get("quality"),
                "source": "scada_historian",
            },
        )

    def fetch_signals(self, *, readings: Optional[List[Dict]] = None, **kwargs) -> List[CanonicalSignal]:
        if not readings:
            return []
        results = []
        for reading in readings:
            signal = self.normalize_reading(reading)
            if signal:
                results.append(signal)
        return results

    def fetch_equipment(self, **kwargs) -> List[CanonicalEquipment]:
        return []

    def fetch_failure_events(self, **kwargs) -> List[CanonicalFailureEvent]:
        return []

    def fetch_work_orders(self, **kwargs) -> List[CanonicalWorkOrder]:
        return []
