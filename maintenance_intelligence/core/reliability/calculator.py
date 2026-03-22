"""Reliability metric calculators (ISO 14224 §10, IEC 61703).

Core metrics:
  MTBF  — Mean Time Between Failures = total_operating_hours / failure_count
  MTTR  — Mean Time To Repair = total_downtime_hours / failure_count
  Availability = MTBF / (MTBF + MTTR)
  Failure rate (λ) = failure_count / total_operating_hours

All calculations use the canonical failure_events table with
failure_start_ts and restoration_ts for downtime derivation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class FailureInterval:
    """A single failure record with timestamps for reliability calculation."""

    event_id: str
    failure_start: datetime
    restoration: Optional[datetime] = None
    downtime_hours: Optional[float] = None

    @property
    def computed_downtime_hours(self) -> Optional[float]:
        if self.downtime_hours is not None:
            return self.downtime_hours
        if self.restoration and self.failure_start:
            delta = self.restoration - self.failure_start
            return max(delta.total_seconds() / 3600, 0)
        return None


@dataclass
class ReliabilityMetrics:
    """Calculated reliability metrics for an equipment unit or group."""

    equipment_unit_id: Optional[str] = None
    asset_id: Optional[str] = None
    observation_start: Optional[datetime] = None
    observation_end: Optional[datetime] = None
    observation_hours: Optional[float] = None
    failure_count: int = 0
    total_downtime_hours: float = 0.0
    total_operating_hours: float = 0.0
    mtbf_hours: Optional[float] = None
    mttr_hours: Optional[float] = None
    availability: Optional[float] = None
    failure_rate: Optional[float] = None
    failures_with_downtime: int = 0
    failures_without_downtime: int = 0
    longest_downtime_hours: Optional[float] = None
    shortest_downtime_hours: Optional[float] = None
    failure_mode_distribution: Dict[str, int] = field(default_factory=dict)
    failure_cause_distribution: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
            elif isinstance(v, float) and v is not None:
                d[k] = round(v, 4)
            else:
                d[k] = v
        return d


def calculate_mtbf(
    operating_hours: float, failure_count: int
) -> Optional[float]:
    """MTBF = total operating hours / number of failures."""
    if failure_count <= 0 or operating_hours <= 0:
        return None
    return operating_hours / failure_count


def calculate_mttr(
    total_downtime_hours: float, failure_count: int
) -> Optional[float]:
    """MTTR = total downtime hours / number of failures with restoration."""
    if failure_count <= 0:
        return None
    return total_downtime_hours / failure_count


def calculate_availability(
    mtbf: Optional[float], mttr: Optional[float]
) -> Optional[float]:
    """Inherent availability A = MTBF / (MTBF + MTTR).

    Returns value between 0 and 1.
    """
    if mtbf is None or mttr is None:
        return None
    denominator = mtbf + mttr
    if denominator <= 0:
        return None
    return mtbf / denominator


def calculate_failure_rate(
    operating_hours: float, failure_count: int
) -> Optional[float]:
    """Failure rate λ = failures / operating hours.

    Returns failures per hour. Multiply by 1_000_000 for failures per
    million hours if needed.
    """
    if failure_count <= 0 or operating_hours <= 0:
        return None
    return failure_count / operating_hours


def calculate_reliability(
    failures: Sequence[FailureInterval],
    *,
    observation_start: Optional[datetime] = None,
    observation_end: Optional[datetime] = None,
    equipment_unit_id: Optional[str] = None,
    asset_id: Optional[str] = None,
) -> ReliabilityMetrics:
    """Calculate full reliability metrics from a sequence of failure intervals.

    Args:
        failures: chronologically ordered failure records
        observation_start: start of observation window (defaults to first failure)
        observation_end: end of observation window (defaults to now)
        equipment_unit_id: canonical equipment reference
        asset_id: legacy asset reference

    Returns:
        ReliabilityMetrics with MTBF, MTTR, availability, failure rate,
        and distribution breakdowns.
    """
    if not failures:
        return ReliabilityMetrics(
            equipment_unit_id=equipment_unit_id,
            asset_id=asset_id,
            observation_start=observation_start,
            observation_end=observation_end,
        )

    sorted_failures = sorted(failures, key=lambda f: f.failure_start)

    obs_start = observation_start or sorted_failures[0].failure_start
    obs_end = observation_end or datetime.utcnow()
    obs_hours = max((obs_end - obs_start).total_seconds() / 3600, 0)

    failure_count = len(sorted_failures)
    total_downtime = 0.0
    failures_with_dt = 0
    failures_without_dt = 0
    downtimes: List[float] = []

    for f in sorted_failures:
        dt = f.computed_downtime_hours
        if dt is not None and dt >= 0:
            total_downtime += dt
            downtimes.append(dt)
            failures_with_dt += 1
        else:
            failures_without_dt += 1

    operating_hours = max(obs_hours - total_downtime, 0)

    mtbf = calculate_mtbf(operating_hours, failure_count)
    mttr = calculate_mttr(total_downtime, failures_with_dt) if failures_with_dt > 0 else None
    avail = calculate_availability(mtbf, mttr)
    fail_rate = calculate_failure_rate(operating_hours, failure_count)

    return ReliabilityMetrics(
        equipment_unit_id=equipment_unit_id,
        asset_id=asset_id,
        observation_start=obs_start,
        observation_end=obs_end,
        observation_hours=round(obs_hours, 2),
        failure_count=failure_count,
        total_downtime_hours=round(total_downtime, 2),
        total_operating_hours=round(operating_hours, 2),
        mtbf_hours=mtbf,
        mttr_hours=mttr,
        availability=avail,
        failure_rate=fail_rate,
        failures_with_downtime=failures_with_dt,
        failures_without_downtime=failures_without_dt,
        longest_downtime_hours=max(downtimes) if downtimes else None,
        shortest_downtime_hours=min(downtimes) if downtimes else None,
    )
