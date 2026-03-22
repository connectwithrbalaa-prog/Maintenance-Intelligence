"""ISO 14224 failure mode, mechanism, cause, detection method, and maintenance action codes.

Reference data sourced from ISO 14224:2016 Annex B and Tables 4-7.
Used to seed the taxonomy reference tables in PostgreSQL.
"""

FAILURE_MODES = [
    ("AIR", "Abnormal instrument reading", "Instrument reading outside normal range"),
    ("BRD", "Breakdown", "Complete loss of function"),
    ("ERO", "Erosion/wear", "Material loss from erosion or surface wear"),
    ("ELP", "External leakage — process", "Leakage of process medium to environment"),
    ("ELU", "External leakage — utility", "Leakage of utility medium to environment"),
    ("FTS", "Failure to start on demand", "Equipment fails to start when demanded"),
    ("FTO", "Failure to stop on demand", "Equipment fails to stop when demanded"),
    ("FTR", "Failure to regulate", "Inability to regulate output within spec"),
    ("FTC", "Failure to close", "Valve or damper fails to close"),
    ("FTF", "Failure to function", "General loss of intended function"),
    ("HIO", "High output", "Output exceeds specified limits"),
    ("LOO", "Low output", "Output falls below specified limits"),
    ("INL", "Internal leakage", "Leakage across internal boundary"),
    ("OHE", "Overheating", "Temperature exceeds design limits"),
    ("NOI", "Noise", "Abnormal noise indicating degradation"),
    ("PLU", "Plugged/choked", "Flow path blocked or restricted"),
    ("SER", "Spurious operation", "Unintended activation or trip"),
    ("SPO", "Spurious stop", "Unintended shutdown"),
    ("STD", "Structural deficiency", "Cracking, deformation, or structural weakness"),
    ("VIB", "Vibration", "Abnormal vibration levels"),
    ("OTH", "Other", "Failure mode not classified above"),
    ("UNK", "Unknown", "Failure mode could not be determined"),
]

FAILURE_MECHANISMS = [
    ("COR", "Corrosion", "Material degradation from chemical reaction"),
    ("ERO", "Erosion", "Material loss from particle or fluid impingement"),
    ("WEA", "Wear", "Material loss from mechanical contact"),
    ("FAT", "Fatigue", "Cracking from cyclic loading"),
    ("BUR", "Burnout/overheat", "Thermal damage from excessive temperature"),
    ("BLO", "Blockage/plugging", "Obstruction of flow path"),
    ("DEF", "Deformation", "Permanent shape change under load"),
    ("FOL", "Foreign object", "Damage from foreign material ingress"),
    ("MAT", "Material defect", "Inherent material quality issue"),
    ("OVS", "Overspeed", "Operation beyond rated speed"),
    ("OVP", "Overpressure", "Operation beyond rated pressure"),
    ("CAV", "Cavitation", "Vapour bubble formation and collapse"),
    ("SCC", "Stress corrosion cracking", "Combined corrosion and tensile stress"),
    ("COB", "Combined mechanisms", "Multiple concurrent mechanisms"),
    ("OTH", "Other mechanism", "Mechanism not classified above"),
    ("UNK", "Unknown mechanism", "Mechanism could not be determined"),
]

FAILURE_CAUSES = [
    ("DES", "Design-related", "DESIGN", "Inadequate design, specification, or material selection"),
    ("FAB", "Fabrication/installation", "FABRICATION", "Manufacturing defect or installation error"),
    ("OPC", "Operating conditions", "OPERATION", "Operating outside design envelope or abnormal process"),
    ("MNT", "Maintenance-related", "MAINTENANCE", "Inadequate or incorrect maintenance"),
    ("MGT", "Management-related", "MANAGEMENT", "Organisational, procedural, or resource issues"),
    ("MIS", "Miscellaneous", "MISC", "Cause does not fit other categories"),
    ("UNK", "Unknown", "UNKNOWN", "Cause could not be determined"),
]

MAINTENANCE_ACTIONS = [
    ("REP", "Repair", "CORRECTIVE", "Restore function by repairing damaged item"),
    ("RPL", "Replace", "CORRECTIVE", "Replace failed item with new or refurbished"),
    ("ADJ", "Adjust/realign", "CORRECTIVE", "Adjust settings, alignment, or calibration"),
    ("MOD", "Modify", "CORRECTIVE", "Modify design or configuration to prevent recurrence"),
    ("INS", "Inspect/monitor", "PREVENTIVE", "Periodic inspection or condition monitoring"),
    ("TST", "Function test", "DETECTIVE", "Verify function through testing"),
    ("OVH", "Overhaul", "PREVENTIVE", "Major refurbishment of item"),
    ("CLN", "Clean", "PREVENTIVE", "Remove fouling, debris, or contamination"),
    ("LUB", "Lubricate", "PREVENTIVE", "Apply or replace lubricant"),
    ("CMB", "Combination", "CORRECTIVE", "Multiple maintenance activities performed"),
    ("OTH", "Other", "CORRECTIVE", "Activity not classified above"),
]

DETECTION_METHODS = [
    ("PER", "Periodic maintenance", "Discovered during scheduled PM activity"),
    ("INS", "Inspection", "Discovered during visual or manual inspection"),
    ("DIM", "On-demand", "Discovered when function was demanded"),
    ("MON", "Continuous monitoring", "Detected by SCADA, DCS, or online monitoring"),
    ("PRD", "Production interference", "Detected by impact on production"),
    ("OBS", "Operator observation", "Noticed by operator during routine rounds"),
    ("TST", "Function testing", "Detected during proof or function test"),
    ("OTH", "Other", "Other detection method"),
]
