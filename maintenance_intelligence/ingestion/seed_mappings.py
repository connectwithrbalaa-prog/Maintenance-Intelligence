"""Seed sample SAP PM and Maximo failure code mappings.

Run: python -m maintenance_intelligence.ingestion.seed_mappings

This populates sap_failure_code_map and maximo_failure_code_map with
representative mappings from common CMMS codes to ISO 14224 codes.
"""

from __future__ import annotations

import psycopg2
from maintenance_intelligence.runner.config import Settings

SAP_MAPPINGS = [
    ("OBJECT_PART", "BEAR", "Bearing", "failure_mode", "VIB"),
    ("OBJECT_PART", "SEAL", "Seal/packing", "failure_mode", "ELP"),
    ("OBJECT_PART", "IMPE", "Impeller", "failure_mode", "LOO"),
    ("OBJECT_PART", "MOTO", "Motor", "failure_mode", "FTS"),
    ("OBJECT_PART", "COUP", "Coupling", "failure_mode", "VIB"),
    ("OBJECT_PART", "GEAR", "Gearbox", "failure_mode", "NOI"),
    ("DAMAGE", "WEAR", "Wear/abrasion", "failure_mechanism", "WEA"),
    ("DAMAGE", "CORR", "Corrosion", "failure_mechanism", "COR"),
    ("DAMAGE", "FATI", "Fatigue crack", "failure_mechanism", "FAT"),
    ("DAMAGE", "EROS", "Erosion", "failure_mechanism", "ERO"),
    ("DAMAGE", "BURN", "Burnout/overheat", "failure_mechanism", "BUR"),
    ("DAMAGE", "BLOC", "Blockage", "failure_mechanism", "BLO"),
    ("DAMAGE", "DEFO", "Deformation", "failure_mechanism", "DEF"),
    ("DAMAGE", "CAVI", "Cavitation", "failure_mechanism", "CAV"),
    ("CAUSE", "OPER", "Operating error/conditions", "failure_cause", "OPC"),
    ("CAUSE", "MAIN", "Maintenance-related", "failure_cause", "MNT"),
    ("CAUSE", "DESI", "Design deficiency", "failure_cause", "DES"),
    ("CAUSE", "FABR", "Fabrication/installation", "failure_cause", "FAB"),
    ("CAUSE", "MATE", "Material defect", "failure_cause", "DES"),
    ("CAUSE", "UNKN", "Unknown", "failure_cause", "UNK"),
    ("ACTIVITY", "REPA", "Repair", "maintenance_action", "REP"),
    ("ACTIVITY", "REPL", "Replace", "maintenance_action", "RPL"),
    ("ACTIVITY", "ADJU", "Adjust/realign", "maintenance_action", "ADJ"),
    ("ACTIVITY", "OVER", "Overhaul", "maintenance_action", "OVH"),
    ("ACTIVITY", "CLEA", "Clean", "maintenance_action", "CLN"),
    ("ACTIVITY", "LUBR", "Lubricate", "maintenance_action", "LUB"),
    ("ACTIVITY", "INSP", "Inspect", "maintenance_action", "INS"),
    ("ACTIVITY", "TEST", "Function test", "maintenance_action", "TST"),
]

MAXIMO_MAPPINGS = [
    ("PROBLEM", "VIBRATION", "Abnormal vibration", "failure_mode", "VIB"),
    ("PROBLEM", "LEAK", "External leak", "failure_mode", "ELP"),
    ("PROBLEM", "OVERHEAT", "Overheating", "failure_mode", "OHE"),
    ("PROBLEM", "NOSTART", "Failure to start", "failure_mode", "FTS"),
    ("PROBLEM", "NOSTOP", "Failure to stop", "failure_mode", "FTO"),
    ("PROBLEM", "LOWOUTPUT", "Low output", "failure_mode", "LOO"),
    ("PROBLEM", "HIGHOUTPUT", "High output", "failure_mode", "HIO"),
    ("PROBLEM", "NOISE", "Abnormal noise", "failure_mode", "NOI"),
    ("PROBLEM", "SPURIOUS", "Spurious operation", "failure_mode", "SER"),
    ("PROBLEM", "BREAKDOWN", "Breakdown", "failure_mode", "BRD"),
    ("CAUSE", "WEAR", "Wear", "failure_cause", "MNT"),
    ("CAUSE", "CORROSION", "Corrosion", "failure_cause", "OPC"),
    ("CAUSE", "DESIGN", "Design issue", "failure_cause", "DES"),
    ("CAUSE", "INSTALLATION", "Installation error", "failure_cause", "FAB"),
    ("CAUSE", "OPERATION", "Operating conditions", "failure_cause", "OPC"),
    ("CAUSE", "MATERIAL", "Material defect", "failure_cause", "DES"),
    ("CAUSE", "UNKNOWN", "Unknown cause", "failure_cause", "UNK"),
    ("REMEDY", "REPAIR", "Repair", "maintenance_action", "REP"),
    ("REMEDY", "REPLACE", "Replace", "maintenance_action", "RPL"),
    ("REMEDY", "ADJUST", "Adjust", "maintenance_action", "ADJ"),
    ("REMEDY", "OVERHAUL", "Overhaul", "maintenance_action", "OVH"),
    ("REMEDY", "CLEAN", "Clean", "maintenance_action", "CLN"),
    ("REMEDY", "LUBRICATE", "Lubricate", "maintenance_action", "LUB"),
    ("REMEDY", "INSPECT", "Inspect", "maintenance_action", "INS"),
    ("REMEDY", "MODIFY", "Modify", "maintenance_action", "MOD"),
]


def seed(conn=None):
    close_conn = False
    if conn is None:
        settings = Settings()
        conn = psycopg2.connect(settings.pg_dsn)
        close_conn = True

    try:
        with conn:
            with conn.cursor() as cur:
                for domain, code, desc, concept, iso_code in SAP_MAPPINGS:
                    cur.execute(
                        """INSERT INTO sap_failure_code_map
                           (source_domain, source_code, description, iso_concept, iso_standard_code)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT DO NOTHING""",
                        (domain, code, desc, concept, iso_code),
                    )
                for domain, code, desc, concept, iso_code in MAXIMO_MAPPINGS:
                    cur.execute(
                        """INSERT INTO maximo_failure_code_map
                           (source_domain, source_code, description, iso_concept, iso_standard_code)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT DO NOTHING""",
                        (domain, code, desc, concept, iso_code),
                    )
        print(f"Seeded {len(SAP_MAPPINGS)} SAP mappings and {len(MAXIMO_MAPPINGS)} Maximo mappings.")
    finally:
        if close_conn:
            conn.close()


if __name__ == "__main__":
    seed()
