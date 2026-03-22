"""Seed a demo-grade upstream Oil & Gas pilot site.

Populates the full ISO 14224 hierarchy (L3–L8) for an offshore production
platform with realistic equipment, sub-units, components, sample failure
events, and SCADA tag mappings.

Run: python -m maintenance_intelligence.core.taxonomy.seed_pilot_site

Idempotent — uses ON CONFLICT DO NOTHING on all inserts.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import psycopg2

from maintenance_intelligence.runner.config import Settings

TENANT_ID = "demo-og"

# ── L3: Site ──

SITE = {
    "site_id": "GULF-01",
    "bu_code": "UP",
    "name": "Gulf of Mexico Field Development",
    "basin_region": "Gulf of Mexico — Deepwater",
    "onshore_offshore": "OFFSHORE",
    "country": "US",
    "geo_latitude": 28.15,
    "geo_longitude": -89.45,
    "tenant_id": TENANT_ID,
}

# ── L4: Facilities ──

FACILITIES = [
    {"facility_id": "FAC-PLATFORM", "site_id": "GULF-01", "facility_type": "OFFSHORE_PLATFORM", "name": "Production Platform Alpha"},
    {"facility_id": "FAC-WELLPAD", "site_id": "GULF-01", "facility_type": "WELL_CLUSTER", "name": "Well Pad Cluster W-1"},
]

# ── L5: Systems ──

SYSTEMS = [
    {"system_id": "SYS-GASCOMP", "facility_id": "FAC-PLATFORM", "system_type": "GAS_COMPRESSION", "system_group": "PROCESS", "name": "Gas Compression Train"},
    {"system_id": "SYS-SEPARATION", "facility_id": "FAC-PLATFORM", "system_type": "SEPARATION", "system_group": "PROCESS", "name": "Production Separation"},
    {"system_id": "SYS-OILEXPORT", "facility_id": "FAC-PLATFORM", "system_type": "OIL_EXPORT", "system_group": "PROCESS", "name": "Oil Export and Pumping"},
    {"system_id": "SYS-METERING", "facility_id": "FAC-PLATFORM", "system_type": "METERING", "system_group": "PROCESS", "name": "Fiscal Metering"},
    {"system_id": "SYS-ELECDIST", "facility_id": "FAC-PLATFORM", "system_type": "ELEC_DIST", "system_group": "UTILITIES", "name": "Electrical Generation and Distribution"},
    {"system_id": "SYS-INSTRAIR", "facility_id": "FAC-PLATFORM", "system_type": "INSTR_AIR", "system_group": "UTILITIES", "name": "Instrument Air"},
    {"system_id": "SYS-FIREWATER", "facility_id": "FAC-PLATFORM", "system_type": "FIRE_WATER", "system_group": "SAFETY", "name": "Fire Water and Safety Systems"},
    {"system_id": "SYS-WELLHEAD", "facility_id": "FAC-WELLPAD", "system_type": "WELLHEAD", "system_group": "PROCESS", "name": "Wellhead and Xmas Trees"},
]

# ── L6: Equipment Units ──

EQUIPMENT = [
    # Gas Compression
    {"equipment_unit_id": "EQ-CT301A", "system_id": "SYS-GASCOMP", "tag": "CT-301A", "iso_equipment_class": "CENTRIFUGAL_COMPRESSOR", "equipment_family": "EF-ROT", "oem_name": "Solar Turbines", "oem_model": "C65", "criticality": "CRITICAL", "service_medium": "GAS", "duty_type": "CONTINUOUS", "safety_critical": True, "rated_power_kw": 6500, "rated_speed_rpm": 11000, "design_pressure_bar": 85, "design_temperature_c": 180},
    {"equipment_unit_id": "EQ-CT301B", "system_id": "SYS-GASCOMP", "tag": "CT-301B", "iso_equipment_class": "CENTRIFUGAL_COMPRESSOR", "equipment_family": "EF-ROT", "oem_name": "Solar Turbines", "oem_model": "C65", "criticality": "HIGH", "service_medium": "GAS", "duty_type": "STANDBY", "safety_critical": True, "rated_power_kw": 6500, "rated_speed_rpm": 11000, "design_pressure_bar": 85, "design_temperature_c": 180},
    # Separation
    {"equipment_unit_id": "EQ-PS105A", "system_id": "SYS-SEPARATION", "tag": "PS-105A", "iso_equipment_class": "CENTRIFUGAL_PUMP", "equipment_family": "EF-ROT", "oem_name": "Flowserve", "oem_model": "HPX-2000", "criticality": "HIGH", "service_medium": "OIL", "duty_type": "CONTINUOUS", "safety_critical": False, "rated_power_kw": 250, "rated_speed_rpm": 3560},
    {"equipment_unit_id": "EQ-PS105B", "system_id": "SYS-SEPARATION", "tag": "PS-105B", "iso_equipment_class": "CENTRIFUGAL_PUMP", "equipment_family": "EF-ROT", "oem_name": "Flowserve", "oem_model": "HPX-2000", "criticality": "HIGH", "service_medium": "OIL", "duty_type": "STANDBY", "safety_critical": False, "rated_power_kw": 250, "rated_speed_rpm": 3560},
    {"equipment_unit_id": "EQ-PS105C", "system_id": "SYS-SEPARATION", "tag": "PS-105C", "iso_equipment_class": "CENTRIFUGAL_PUMP", "equipment_family": "EF-ROT", "oem_name": "Flowserve", "oem_model": "HPX-2000", "criticality": "MEDIUM", "service_medium": "OIL", "duty_type": "STANDBY", "safety_critical": False, "rated_power_kw": 250, "rated_speed_rpm": 3560},
    {"equipment_unit_id": "EQ-V201", "system_id": "SYS-SEPARATION", "tag": "V-201", "iso_equipment_class": "PRESSURE_VESSEL", "equipment_family": "EF-STAT", "oem_name": "Cameron", "oem_model": "HP-SEP-3600", "criticality": "CRITICAL", "service_medium": "MULTIPHASE", "duty_type": "CONTINUOUS", "safety_critical": True, "design_pressure_bar": 120, "design_temperature_c": 95},
    # Oil Export
    {"equipment_unit_id": "EQ-PS301A", "system_id": "SYS-OILEXPORT", "tag": "PS-301A", "iso_equipment_class": "CENTRIFUGAL_PUMP", "equipment_family": "EF-ROT", "oem_name": "Sulzer", "oem_model": "MSD-RO 32-200", "criticality": "HIGH", "service_medium": "OIL", "duty_type": "CONTINUOUS", "safety_critical": False, "rated_power_kw": 450, "rated_speed_rpm": 2980},
    {"equipment_unit_id": "EQ-PS301B", "system_id": "SYS-OILEXPORT", "tag": "PS-301B", "iso_equipment_class": "CENTRIFUGAL_PUMP", "equipment_family": "EF-ROT", "oem_name": "Sulzer", "oem_model": "MSD-RO 32-200", "criticality": "MEDIUM", "service_medium": "OIL", "duty_type": "STANDBY", "safety_critical": False, "rated_power_kw": 450, "rated_speed_rpm": 2980},
    # Electrical
    {"equipment_unit_id": "EQ-GT201", "system_id": "SYS-ELECDIST", "tag": "GT-201", "iso_equipment_class": "GAS_TURBINE", "equipment_family": "EF-ROT", "oem_name": "GE Vernova", "oem_model": "LM2500", "criticality": "CRITICAL", "service_medium": "GAS", "duty_type": "CONTINUOUS", "safety_critical": True, "rated_power_kw": 25000, "rated_speed_rpm": 3600, "design_temperature_c": 550},
    {"equipment_unit_id": "EQ-GT202", "system_id": "SYS-ELECDIST", "tag": "GT-202", "iso_equipment_class": "GAS_TURBINE", "equipment_family": "EF-ROT", "oem_name": "GE Vernova", "oem_model": "LM2500", "criticality": "HIGH", "service_medium": "GAS", "duty_type": "STANDBY", "safety_critical": True, "rated_power_kw": 25000, "rated_speed_rpm": 3600, "design_temperature_c": 550},
    {"equipment_unit_id": "EQ-TR101", "system_id": "SYS-ELECDIST", "tag": "TR-101", "iso_equipment_class": "TRANSFORMER", "equipment_family": "EF-ELEC", "oem_name": "ABB", "oem_model": "RESIBLOC", "criticality": "HIGH", "service_medium": "AIR", "duty_type": "CONTINUOUS", "safety_critical": False},
    {"equipment_unit_id": "EQ-MCC01", "system_id": "SYS-ELECDIST", "tag": "MCC-01", "iso_equipment_class": "MCC", "equipment_family": "EF-ELEC", "oem_name": "Schneider Electric", "oem_model": "Okken", "criticality": "HIGH", "duty_type": "CONTINUOUS", "safety_critical": False},
    # Instrument Air
    {"equipment_unit_id": "EQ-K401", "system_id": "SYS-INSTRAIR", "tag": "K-401", "iso_equipment_class": "PACKAGE_COMPRESSOR", "equipment_family": "EF-PACK", "oem_name": "Atlas Copco", "oem_model": "ZR 250", "criticality": "HIGH", "service_medium": "AIR", "duty_type": "CONTINUOUS", "safety_critical": False, "rated_power_kw": 250},
    # Safety Systems
    {"equipment_unit_id": "EQ-ESD01", "system_id": "SYS-FIREWATER", "tag": "ESD-01", "iso_equipment_class": "ESD_SYSTEM", "equipment_family": "EF-SAFE", "oem_name": "Honeywell", "oem_model": "Safety Manager SC", "criticality": "CRITICAL", "safety_critical": True},
    {"equipment_unit_id": "EQ-FGS01", "system_id": "SYS-FIREWATER", "tag": "FGS-01", "iso_equipment_class": "FIRE_GAS_SYSTEM", "equipment_family": "EF-SAFE", "oem_name": "Detector Electronics", "oem_model": "FlexVu UD", "criticality": "CRITICAL", "safety_critical": True},
    # Metering
    {"equipment_unit_id": "EQ-FT101", "system_id": "SYS-METERING", "tag": "FT-101", "iso_equipment_class": "TRANSMITTER", "equipment_family": "EF-INST", "oem_name": "Emerson", "oem_model": "Micro Motion F300", "criticality": "HIGH", "service_medium": "OIL", "duty_type": "CONTINUOUS", "safety_critical": False},
    {"equipment_unit_id": "EQ-CV201", "system_id": "SYS-METERING", "tag": "CV-201", "iso_equipment_class": "CONTROL_VALVE", "equipment_family": "EF-INST", "oem_name": "Fisher", "oem_model": "GX", "criticality": "MEDIUM", "service_medium": "OIL", "duty_type": "CONTINUOUS", "safety_critical": False},
    # Wellhead
    {"equipment_unit_id": "EQ-WH001", "system_id": "SYS-WELLHEAD", "tag": "WH-001", "iso_equipment_class": "ONOFF_VALVE", "equipment_family": "EF-INST", "oem_name": "Cameron", "oem_model": "DG 10000 XMT", "criticality": "CRITICAL", "service_medium": "MULTIPHASE", "duty_type": "CONTINUOUS", "safety_critical": True, "design_pressure_bar": 690},
]

# ── L7: Sub-units ──

SUBUNITS = [
    # CT-301A (Compressor Train)
    {"subunit_id": "SU-CT301A-DRV", "equipment_unit_id": "EQ-CT301A", "subunit_type_code": "DRIVER", "description": "Gas turbine driver section"},
    {"subunit_id": "SU-CT301A-CMP", "equipment_unit_id": "EQ-CT301A", "subunit_type_code": "PUMP_COMP_SECTION", "description": "Centrifugal compressor section"},
    {"subunit_id": "SU-CT301A-SEL", "equipment_unit_id": "EQ-CT301A", "subunit_type_code": "SEAL_SYSTEM", "description": "Dry gas seal system"},
    {"subunit_id": "SU-CT301A-BRG", "equipment_unit_id": "EQ-CT301A", "subunit_type_code": "BEARING_SYSTEM", "description": "Journal and thrust bearing assembly"},
    {"subunit_id": "SU-CT301A-LUB", "equipment_unit_id": "EQ-CT301A", "subunit_type_code": "LUBE_OIL_SYSTEM", "description": "Lube oil supply, filtration, and cooler"},
    {"subunit_id": "SU-CT301A-CPL", "equipment_unit_id": "EQ-CT301A", "subunit_type_code": "COUPLING", "description": "Flexible disc coupling"},
    # PS-105B (Pump Skid)
    {"subunit_id": "SU-PS105B-DRV", "equipment_unit_id": "EQ-PS105B", "subunit_type_code": "DRIVER", "description": "Electric motor driver"},
    {"subunit_id": "SU-PS105B-PMP", "equipment_unit_id": "EQ-PS105B", "subunit_type_code": "PUMP_COMP_SECTION", "description": "Pump impeller and casing"},
    {"subunit_id": "SU-PS105B-SEL", "equipment_unit_id": "EQ-PS105B", "subunit_type_code": "SEAL_SYSTEM", "description": "Mechanical seal cartridge"},
    {"subunit_id": "SU-PS105B-BRG", "equipment_unit_id": "EQ-PS105B", "subunit_type_code": "BEARING_SYSTEM", "description": "Pump bearing assembly"},
    # GT-201 (Gas Turbine Generator)
    {"subunit_id": "SU-GT201-CMP", "equipment_unit_id": "EQ-GT201", "subunit_type_code": "PUMP_COMP_SECTION", "description": "Axial compressor section"},
    {"subunit_id": "SU-GT201-CMB", "equipment_unit_id": "EQ-GT201", "subunit_type_code": "DRIVER", "description": "Combustion section (cans 1-12)"},
    {"subunit_id": "SU-GT201-TRB", "equipment_unit_id": "EQ-GT201", "subunit_type_code": "DRIVER", "description": "Power turbine section"},
    {"subunit_id": "SU-GT201-BRG", "equipment_unit_id": "EQ-GT201", "subunit_type_code": "BEARING_SYSTEM", "description": "Turbine journal bearings"},
    {"subunit_id": "SU-GT201-LUB", "equipment_unit_id": "EQ-GT201", "subunit_type_code": "LUBE_OIL_SYSTEM", "description": "Lube and hydraulic oil system"},
    # V-201 (Separator Vessel)
    {"subunit_id": "SU-V201-SHL", "equipment_unit_id": "EQ-V201", "subunit_type_code": "SHELL", "description": "Pressure vessel shell and heads"},
    {"subunit_id": "SU-V201-INT", "equipment_unit_id": "EQ-V201", "subunit_type_code": "INTERNALS", "description": "Separator internals (weir plates, coalescer packs)"},
    {"subunit_id": "SU-V201-NOZ", "equipment_unit_id": "EQ-V201", "subunit_type_code": "NOZZLE", "description": "Inlet and outlet nozzles with isolation valves"},
    {"subunit_id": "SU-V201-RLF", "equipment_unit_id": "EQ-V201", "subunit_type_code": "SUPPORT", "description": "Relief valve and safety instrumentation"},
]

# ── L8: Components ──

COMPONENTS = [
    # CT-301A bearings and seals
    {"component_id": "C-CT301A-BRG-DE", "subunit_id": "SU-CT301A-BRG", "component_type_code": "BEARING_RADIAL", "description": "Drive-end radial journal bearing (SKF 7320 BECBM)"},
    {"component_id": "C-CT301A-BRG-NDE", "subunit_id": "SU-CT301A-BRG", "component_type_code": "BEARING_RADIAL", "description": "Non-drive-end radial journal bearing"},
    {"component_id": "C-CT301A-BRG-THR", "subunit_id": "SU-CT301A-BRG", "component_type_code": "BEARING_THRUST", "description": "Kingsbury-type thrust bearing"},
    {"component_id": "C-CT301A-SEL-DE", "subunit_id": "SU-CT301A-SEL", "component_type_code": "SEAL_MECH", "description": "Drive-end dry gas seal cartridge"},
    {"component_id": "C-CT301A-SEL-NDE", "subunit_id": "SU-CT301A-SEL", "component_type_code": "SEAL_MECH", "description": "Non-drive-end dry gas seal cartridge"},
    {"component_id": "C-CT301A-CPL", "subunit_id": "SU-CT301A-CPL", "component_type_code": "COUPLING_ELEMENT", "description": "Flexible disc coupling element"},
    {"component_id": "C-CT301A-IMP", "subunit_id": "SU-CT301A-CMP", "component_type_code": "IMPELLER", "description": "First-stage impeller (Inconel 718)"},
    {"component_id": "C-CT301A-FLT", "subunit_id": "SU-CT301A-LUB", "component_type_code": "FILTER", "description": "Lube oil duplex filter element"},
    # PS-105B seals
    {"component_id": "C-PS105B-SEL", "subunit_id": "SU-PS105B-SEL", "component_type_code": "SEAL_MECH", "description": "Cartridge mechanical seal (John Crane 4620)"},
    {"component_id": "C-PS105B-IMP", "subunit_id": "SU-PS105B-PMP", "component_type_code": "IMPELLER", "description": "Enclosed impeller (316SS)"},
    {"component_id": "C-PS105B-BRG", "subunit_id": "SU-PS105B-BRG", "component_type_code": "BEARING_RADIAL", "description": "Deep groove ball bearing"},
    # GT-201 combustion and turbine
    {"component_id": "C-GT201-ROTOR", "subunit_id": "SU-GT201-TRB", "component_type_code": "ROTOR", "description": "Power turbine rotor assembly"},
    {"component_id": "C-GT201-NOZZLE", "subunit_id": "SU-GT201-CMB", "component_type_code": "IMPELLER", "description": "Fuel nozzle tip assembly (12 per ring)"},
    {"component_id": "C-GT201-BRG-FWD", "subunit_id": "SU-GT201-BRG", "component_type_code": "BEARING_RADIAL", "description": "Forward journal bearing"},
    {"component_id": "C-GT201-BRG-AFT", "subunit_id": "SU-GT201-BRG", "component_type_code": "BEARING_RADIAL", "description": "Aft journal bearing"},
    {"component_id": "C-GT201-FLT", "subunit_id": "SU-GT201-LUB", "component_type_code": "FILTER", "description": "Lube oil filter cartridge"},
]

# ── Sample failure events ──

NOW = datetime.utcnow()

FAILURE_EVENTS = [
    {
        "event_id": "FE-OG-001",
        "tenant_id": TENANT_ID, "source_system": "SCADA",
        "equipment_unit_id": "EQ-CT301A", "component_id": "C-CT301A-BRG-DE",
        "asset_id": "CT-301A",
        "failure_mode_code": "VIB", "failure_mechanism_code": "WEA",
        "failure_cause_code": "MNT", "maintenance_action_code": "RPL",
        "detection_method_code": "MON", "consequence_code": "PRODUCTION_LOSS",
        "impact_level": "MAJOR", "severity": "high", "kind": "alarm",
        "summary": "Drive-end bearing vibration exceeded 9.4 mm/s RMS — bearing replacement completed",
        "failure_start_ts": NOW - timedelta(days=45, hours=6),
        "restoration_ts": NOW - timedelta(days=44, hours=14),
        "downtime_hours": 16,
    },
    {
        "event_id": "FE-OG-002",
        "tenant_id": TENANT_ID, "source_system": "SCADA",
        "equipment_unit_id": "EQ-CT301A", "component_id": "C-CT301A-SEL-DE",
        "asset_id": "CT-301A",
        "failure_mode_code": "ELP", "failure_mechanism_code": "WEA",
        "failure_cause_code": "OPC", "maintenance_action_code": "RPL",
        "detection_method_code": "MON", "consequence_code": "NONE",
        "impact_level": "MINOR", "severity": "medium", "kind": "anomaly",
        "summary": "Dry gas seal primary vent flow increasing — seal cartridge replaced at next window",
        "failure_start_ts": NOW - timedelta(days=120, hours=3),
        "restoration_ts": NOW - timedelta(days=118),
        "downtime_hours": 24,
    },
    {
        "event_id": "FE-OG-003",
        "tenant_id": TENANT_ID, "source_system": "SCADA",
        "equipment_unit_id": "EQ-PS105B", "component_id": "C-PS105B-SEL",
        "asset_id": "PS-105B",
        "failure_mode_code": "ELP", "failure_mechanism_code": "WEA",
        "failure_cause_code": "OPC", "maintenance_action_code": "RPL",
        "detection_method_code": "MON", "consequence_code": "NONE",
        "impact_level": "MINOR", "severity": "medium", "kind": "anomaly",
        "summary": "Mechanical seal oil pressure drop — seal replaced during planned pump swap",
        "failure_start_ts": NOW - timedelta(days=30, hours=2),
        "restoration_ts": NOW - timedelta(days=29, hours=18),
        "downtime_hours": 8,
    },
    {
        "event_id": "FE-OG-004",
        "tenant_id": TENANT_ID, "source_system": "SCADA",
        "equipment_unit_id": "EQ-GT201", "component_id": "C-GT201-NOZZLE",
        "asset_id": "GT-201",
        "failure_mode_code": "OHE", "failure_mechanism_code": "BUR",
        "failure_cause_code": "OPC", "maintenance_action_code": "RPL",
        "detection_method_code": "MON", "consequence_code": "PRODUCTION_LOSS",
        "impact_level": "MAJOR", "severity": "high", "kind": "alarm",
        "summary": "EGT spread widened to 38°C on cans 7-8 — fuel nozzle tips replaced during planned outage",
        "failure_start_ts": NOW - timedelta(days=15, hours=8),
        "restoration_ts": NOW - timedelta(days=13),
        "downtime_hours": 48,
    },
    {
        "event_id": "FE-OG-005",
        "tenant_id": TENANT_ID, "source_system": "SCADA",
        "equipment_unit_id": "EQ-GT201", "component_id": "C-GT201-BRG-FWD",
        "asset_id": "GT-201",
        "failure_mode_code": "VIB", "failure_mechanism_code": "WEA",
        "failure_cause_code": "MNT", "maintenance_action_code": "INS",
        "detection_method_code": "MON", "consequence_code": "NONE",
        "impact_level": "MINOR", "severity": "medium", "kind": "anomaly",
        "summary": "Forward bearing vibration trending upward — inspection scheduled",
        "failure_start_ts": NOW - timedelta(days=90, hours=4),
        "restoration_ts": NOW - timedelta(days=89, hours=20),
        "downtime_hours": 8,
    },
    {
        "event_id": "FE-OG-006",
        "tenant_id": TENANT_ID, "source_system": "MANUAL",
        "equipment_unit_id": "EQ-PS301A", "component_id": None,
        "asset_id": "PS-301A",
        "failure_mode_code": "FTS", "failure_mechanism_code": "MAT",
        "failure_cause_code": "FAB", "maintenance_action_code": "REP",
        "detection_method_code": "DIM", "consequence_code": "PRODUCTION_LOSS",
        "impact_level": "MAJOR", "severity": "high", "kind": "alarm",
        "summary": "Export pump failed to start on demand — motor contactor replaced",
        "failure_start_ts": NOW - timedelta(days=60, hours=1),
        "restoration_ts": NOW - timedelta(days=59, hours=19),
        "downtime_hours": 6,
    },
    {
        "event_id": "FE-OG-007",
        "tenant_id": TENANT_ID, "source_system": "SCADA",
        "equipment_unit_id": "EQ-V201",
        "asset_id": "V-201",
        "failure_mode_code": "INL", "failure_mechanism_code": "COR",
        "failure_cause_code": "OPC", "maintenance_action_code": "REP",
        "detection_method_code": "INS", "consequence_code": "NONE",
        "impact_level": "MINOR", "severity": "low", "kind": "anomaly",
        "summary": "Internal corrosion detected on weir plate during scheduled inspection — plate repaired",
        "failure_start_ts": NOW - timedelta(days=180),
        "restoration_ts": NOW - timedelta(days=178),
        "downtime_hours": 36,
    },
    {
        "event_id": "FE-OG-008",
        "tenant_id": TENANT_ID, "source_system": "SCADA",
        "equipment_unit_id": "EQ-K401",
        "asset_id": "K-401",
        "failure_mode_code": "OHE", "failure_mechanism_code": "BLO",
        "failure_cause_code": "MNT", "maintenance_action_code": "CLN",
        "detection_method_code": "MON", "consequence_code": "NONE",
        "impact_level": "MINOR", "severity": "medium", "kind": "alarm",
        "summary": "Instrument air compressor intercooler fouled — cleaned and returned to service",
        "failure_start_ts": NOW - timedelta(days=75, hours=5),
        "restoration_ts": NOW - timedelta(days=75),
        "downtime_hours": 5,
    },
]


def seed(conn=None):
    close = conn is None
    if conn is None:
        settings = Settings()
        conn = psycopg2.connect(settings.pg_dsn)

    try:
        with conn:
            with conn.cursor() as cur:
                # L3: Site
                cur.execute(
                    """INSERT INTO sites (site_id, bu_code, name, basin_region, onshore_offshore, country, geo_latitude, geo_longitude, tenant_id)
                       VALUES (%(site_id)s, %(bu_code)s, %(name)s, %(basin_region)s, %(onshore_offshore)s, %(country)s, %(geo_latitude)s, %(geo_longitude)s, %(tenant_id)s)
                       ON CONFLICT (site_id) DO NOTHING""",
                    SITE,
                )

                # L4: Facilities
                for f in FACILITIES:
                    cur.execute(
                        "INSERT INTO facilities (facility_id, site_id, facility_type, name) VALUES (%(facility_id)s, %(site_id)s, %(facility_type)s, %(name)s) ON CONFLICT (facility_id) DO NOTHING", f)

                # L5: Systems
                for s in SYSTEMS:
                    cur.execute(
                        "INSERT INTO systems (system_id, facility_id, system_type, system_group, name) VALUES (%(system_id)s, %(facility_id)s, %(system_type)s, %(system_group)s, %(name)s) ON CONFLICT (system_id) DO NOTHING", s)

                # L6: Equipment
                for e in EQUIPMENT:
                    path = f"GULF-01/{e.get('system_id', '')}/{e['tag']}"
                    cur.execute(
                        """INSERT INTO equipment_units (equipment_unit_id, system_id, tag, iso_equipment_class, equipment_family,
                           oem_name, oem_model, criticality, service_medium, duty_type, safety_critical,
                           rated_power_kw, rated_speed_rpm, design_pressure_bar, design_temperature_c,
                           tenant_id, hierarchy_path)
                           VALUES (%(equipment_unit_id)s, %(system_id)s, %(tag)s, %(iso_equipment_class)s, %(equipment_family)s,
                           %(oem_name)s, %(oem_model)s, %(criticality)s, %(service_medium)s, %(duty_type)s, %(safety_critical)s,
                           %(rated_power_kw)s, %(rated_speed_rpm)s, %(design_pressure_bar)s, %(design_temperature_c)s,
                           %(tenant_id)s, %(hierarchy_path)s)
                           ON CONFLICT (equipment_unit_id) DO NOTHING""",
                        {
                         "equipment_unit_id": e["equipment_unit_id"], "system_id": e["system_id"],
                         "tag": e["tag"], "iso_equipment_class": e["iso_equipment_class"],
                         "equipment_family": e.get("equipment_family"), "oem_name": e.get("oem_name"),
                         "oem_model": e.get("oem_model"), "criticality": e.get("criticality"),
                         "service_medium": e.get("service_medium"), "duty_type": e.get("duty_type"),
                         "safety_critical": e.get("safety_critical", False),
                         "rated_power_kw": e.get("rated_power_kw"), "rated_speed_rpm": e.get("rated_speed_rpm"),
                         "design_pressure_bar": e.get("design_pressure_bar"),
                         "design_temperature_c": e.get("design_temperature_c"),
                         "tenant_id": TENANT_ID, "hierarchy_path": path,
                    },
                    )

                # L7: Sub-units
                for su in SUBUNITS:
                    cur.execute(
                        "INSERT INTO subunits (subunit_id, equipment_unit_id, subunit_type_code, description) VALUES (%(subunit_id)s, %(equipment_unit_id)s, %(subunit_type_code)s, %(description)s) ON CONFLICT (subunit_id) DO NOTHING", su)

                # L8: Components
                for c in COMPONENTS:
                    cur.execute(
                        "INSERT INTO components (component_id, subunit_id, component_type_code, description) VALUES (%(component_id)s, %(subunit_id)s, %(component_type_code)s, %(description)s) ON CONFLICT (component_id) DO NOTHING", c)

                # Failure events
                for fe in FAILURE_EVENTS:
                    fe_safe = {
                        "event_id": fe["event_id"], "tenant_id": fe.get("tenant_id"),
                        "source_system": fe["source_system"],
                        "equipment_unit_id": fe.get("equipment_unit_id"),
                        "component_id": fe.get("component_id"),
                        "asset_id": fe.get("asset_id"),
                        "failure_mode_code": fe.get("failure_mode_code"),
                        "failure_mechanism_code": fe.get("failure_mechanism_code"),
                        "failure_cause_code": fe.get("failure_cause_code"),
                        "maintenance_action_code": fe.get("maintenance_action_code"),
                        "detection_method_code": fe.get("detection_method_code"),
                        "consequence_code": fe.get("consequence_code"),
                        "impact_level": fe.get("impact_level"),
                        "severity": fe.get("severity"), "kind": fe.get("kind"),
                        "summary": fe.get("summary"),
                        "failure_start_ts": fe.get("failure_start_ts"),
                        "restoration_ts": fe.get("restoration_ts"),
                        "downtime_hours": fe.get("downtime_hours"),
                    }
                    cur.execute(
                        """INSERT INTO failure_events (event_id, tenant_id, source_system, equipment_unit_id, component_id, asset_id,
                           failure_mode_code, failure_mechanism_code, failure_cause_code, maintenance_action_code,
                           detection_method_code, consequence_code, impact_level, severity, kind, summary,
                           failure_start_ts, restoration_ts, downtime_hours)
                           VALUES (%(event_id)s, %(tenant_id)s, %(source_system)s, %(equipment_unit_id)s, %(component_id)s, %(asset_id)s,
                           %(failure_mode_code)s, %(failure_mechanism_code)s, %(failure_cause_code)s, %(maintenance_action_code)s,
                           %(detection_method_code)s, %(consequence_code)s, %(impact_level)s, %(severity)s, %(kind)s, %(summary)s,
                           %(failure_start_ts)s, %(restoration_ts)s, %(downtime_hours)s)
                           ON CONFLICT (event_id) DO NOTHING""",
                        fe_safe,
                    )

        print(f"Seeded pilot site: 1 site, {len(FACILITIES)} facilities, {len(SYSTEMS)} systems, "
              f"{len(EQUIPMENT)} equipment units, {len(SUBUNITS)} sub-units, {len(COMPONENTS)} components, "
              f"{len(FAILURE_EVENTS)} failure events")

    finally:
        if close:
            conn.close()


if __name__ == "__main__":
    seed()
