"""ISO 14224–aligned asset hierarchy (L1–L8).

Each level maps to ISO 14224 Table 3 — Taxonomic classification:
  L1 Industry → L2 Business Unit → L3 Site → L4 Facility →
  L5 System → L6 Equipment Unit → L7 Sub-unit → L8 Component
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Industry(BaseModel):
    """L1 — Industry classification (ISO 14224 §5.2)."""

    industry_code: str = Field(..., description="NG, OIL, OILGAS")
    name: str
    iso_level: int = Field(default=1, frozen=True)


class BusinessUnit(BaseModel):
    """L2 — Business unit within an industry."""

    bu_code: str = Field(..., description="UP (upstream), MS (midstream), DS (downstream)")
    industry_code: str
    name: str
    iso_level: int = Field(default=2, frozen=True)


class Site(BaseModel):
    """L3 — Physical site / installation (ISO 14224 §5.3)."""

    site_id: str
    bu_code: str
    name: str
    basin_region: Optional[str] = None
    onshore_offshore: Optional[str] = Field(None, description="ONSHORE | OFFSHORE")
    country: Optional[str] = None
    geo_latitude: Optional[float] = None
    geo_longitude: Optional[float] = None
    tenant_id: Optional[str] = None
    iso_level: int = Field(default=3, frozen=True)


class Facility(BaseModel):
    """L4 — Facility within a site (ISO 14224 §5.4)."""

    facility_id: str
    site_id: str
    facility_type: str = Field(
        ...,
        description="OFFSHORE_PLATFORM, CPF, TERMINAL, WELL_CLUSTER, WELL_PAD, FPSO, REFINERY_UNIT",
    )
    name: str
    iso_level: int = Field(default=4, frozen=True)


class System(BaseModel):
    """L5 — Plant system / process area (ISO 14224 §5.5)."""

    system_id: str
    facility_id: str
    system_type: str = Field(
        ...,
        description="SEPARATION, GAS_COMPRESSION, WELLHEAD, XMT, ARTIFICIAL_LIFT, "
        "OIL_EXPORT, GAS_DEHYDRATION, FLARE, METERING, INSTR_AIR, "
        "ELEC_DIST, COOL_WATER, FIRE_WATER, HVAC, DIESEL_GEN, etc.",
    )
    system_group: str = Field(
        ..., description="PROCESS, UTILITIES, SAFETY, SUBSEA"
    )
    name: str
    iso_level: int = Field(default=5, frozen=True)


class EquipmentUnit(BaseModel):
    """L6 — Equipment unit (ISO 14224 §5.6, Annex A).

    This is the primary maintainable item. The iso_equipment_class maps to
    ISO 14224 Annex A equipment class codes.
    """

    equipment_unit_id: str
    system_id: str
    tag: str = Field(..., description="Plant tag, e.g. P-101, K-101A, GT-201")
    iso_equipment_class: str = Field(
        ...,
        description="ISO 14224 Annex A: CENTRIFUGAL_PUMP, RECIP_COMPRESSOR, "
        "CENTRIFUGAL_COMPRESSOR, GAS_TURBINE, STEAM_TURBINE, FAN, "
        "PRESSURE_VESSEL, HEAT_EXCHANGER, COLUMN, TANK, TRANSFORMER, "
        "SWITCHGEAR, MCC, GENERATOR, MOTOR, CONTROL_VALVE, ONOFF_VALVE, "
        "TRANSMITTER, PLC, ANALYZER, DETECTOR, ESD_SYSTEM, "
        "FIRE_GAS_SYSTEM, RELIEF_VALVE, DELUGE_SYSTEM, "
        "PACKAGE_COMPRESSOR, PACKAGE_PUMP, GENSET_SKID, etc.",
    )
    equipment_family: Optional[str] = Field(
        None, description="EF-ROT, EF-STAT, EF-ELEC, EF-INST, EF-SAFE, EF-PACK"
    )
    oem_name: Optional[str] = None
    oem_model: Optional[str] = None
    criticality: Optional[str] = Field(None, description="CRITICAL, HIGH, MEDIUM, LOW")
    service_medium: Optional[str] = Field(
        None, description="OIL, GAS, WATER, CHEMICAL, STEAM, AIR, MULTIPHASE"
    )
    duty_type: Optional[str] = Field(None, description="CONTINUOUS, STANDBY, INTERMITTENT")
    safety_critical: bool = False
    install_date: Optional[date] = None
    design_pressure_bar: Optional[float] = None
    design_temperature_c: Optional[float] = None
    rated_power_kw: Optional[float] = None
    rated_speed_rpm: Optional[float] = None
    tenant_id: Optional[str] = None
    hierarchy_path: Optional[str] = Field(
        None, description="Fully qualified path for fast roll-ups, e.g. SITE-01/FAC-01/SYS-01/EQ-001"
    )
    iso_level: int = Field(default=6, frozen=True)


class SubUnit(BaseModel):
    """L7 — Sub-unit within equipment (ISO 14224 §5.7)."""

    subunit_id: str
    equipment_unit_id: str
    subunit_type_code: str = Field(
        ...,
        description="DRIVER, PUMP_COMP_SECTION, SEAL_SYSTEM, BEARING_SYSTEM, "
        "LUBE_OIL_SYSTEM, COOLING_SYSTEM, COUPLING, SHELL, HEAD, NOZZLE, "
        "INTERNALS, SUPPORT, INSULATION, PRIMARY_WINDING, SECONDARY_WINDING, "
        "TAP_CHANGER, BUSBAR, BREAKER_CELL, ACTUATOR, VALVE_BODY, POSITIONER, "
        "SENSOR, ELECTRONICS_MODULE, LOGIC_SOLVER, IO_MODULE, FIELD_LOOP, etc.",
    )
    description: Optional[str] = None
    iso_level: int = Field(default=7, frozen=True)


class Component(BaseModel):
    """L8 — Maintainable component (ISO 14224 §5.8)."""

    component_id: str
    subunit_id: str
    component_type_code: str = Field(
        ...,
        description="BEARING_RADIAL, BEARING_THRUST, SEAL_MECH, SEAL_PACKING, "
        "IMPELLER, ROTOR, GEAR, OIL_PUMP, COOLER, FILTER, MOTOR_STATOR, "
        "MOTOR_ROTOR, COUPLING_ELEMENT, TRAY, PACKING, TUBE, BUNDLE, "
        "MANWAY, BREAKER, CONTACTOR, FUSE, CT, VT, BUSHING, STEM, TRIM, "
        "SEAT, SENSING_ELEMENT, PCB, ESD_VALVE, SOLENOID, DETECTOR_GAS, etc.",
    )
    description: Optional[str] = None
    iso_level: int = Field(default=8, frozen=True)
