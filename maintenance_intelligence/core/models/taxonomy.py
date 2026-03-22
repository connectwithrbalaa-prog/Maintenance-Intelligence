"""ISO 14224 taxonomy reference models.

These map to the ISO 14224 Annex B tables for failure classification
and ISO 14224 Table 4 for maintenance activities.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ISOFailureMode(BaseModel):
    """ISO 14224 Annex B — Failure mode classification.

    Examples: AIR (Abnormal instrument reading), BRD (Breakdown),
    ERO (Erosion), ELP (External leakage — process medium),
    FTS (Failure to start), FTO (Failure to stop),
    HIO (High output), LOO (Low output), INL (Internal leakage),
    OHE (Overheating), NOI (Noise), SER (Spurious operation),
    STD (Structural deficiency), UST (Unknown), VIB (Vibration).
    """

    code: str = Field(..., description="ISO 14224 failure mode code, e.g. VIB, ELP, FTS")
    name: str
    description: Optional[str] = None
    applicable_equipment_families: Optional[str] = Field(
        None, description="Comma-separated: EF-ROT,EF-STAT,EF-ELEC, etc. Blank = all"
    )


class ISOFailureMechanism(BaseModel):
    """ISO 14224 Annex B — Failure mechanism classification.

    Examples: COR (Corrosion), ERO (Erosion), WEA (Wear),
    FAT (Fatigue), BUR (Burnout/overheat), DEF (Deformation),
    FOL (Foreign object), MAT (Material defect), OVS (Overspeed),
    OVP (Overpressure), COB (Combined mechanisms).
    """

    code: str
    name: str
    description: Optional[str] = None


class ISOFailureCause(BaseModel):
    """ISO 14224 §9.3.3 — Failure cause classification.

    Examples: DES (Design-related), FAB (Fabrication/installation),
    OPC (Operating conditions), MNT (Maintenance/repair),
    MGT (Management), MIS (Miscellaneous), UNK (Unknown).
    """

    code: str
    name: str
    category: Optional[str] = Field(
        None, description="DESIGN, FABRICATION, OPERATION, MAINTENANCE, MANAGEMENT, MISC, UNKNOWN"
    )
    description: Optional[str] = None


class ISOMaintenanceAction(BaseModel):
    """ISO 14224 Table 4 — Maintenance activity classification.

    Examples: REP (Repair), RPL (Replace), ADJ (Adjust/realign),
    MOD (Modify), INS (Inspect/monitor), TST (Function test),
    OVH (Overhaul), CLN (Clean), LUB (Lubricate),
    CMB (Combination of activities).
    """

    code: str
    name: str
    maintenance_category: Optional[str] = Field(
        None, description="CORRECTIVE, PREVENTIVE, DETECTIVE"
    )
    description: Optional[str] = None


class ISODetectionMethod(BaseModel):
    """ISO 14224 §9.3.5 — Detection method classification.

    Examples: PER (Periodic maintenance), INS (Inspection),
    DIM (Demand/on-demand), MON (Continuous monitoring/SCADA),
    PRD (Production interference), OBS (Observation by operator),
    TST (Function testing), OTH (Other).
    """

    code: str
    name: str
    description: Optional[str] = None
