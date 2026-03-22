"""Database queries for reliability calculations.

Pulls failure event data from the canonical failure_events table
and legacy events table, transforms into FailureIntervals for
the reliability calculator.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psycopg2

from maintenance_intelligence.core.reliability.calculator import (
    FailureInterval,
    ReliabilityMetrics,
    calculate_reliability,
)
from maintenance_intelligence.runner.config import Settings


def _pg(settings: Optional[Settings] = None):
    s = settings or Settings()
    return psycopg2.connect(s.pg_dsn)


def get_equipment_reliability(
    equipment_unit_id: str,
    *,
    window_days: int = 365,
    conn=None,
    settings: Optional[Settings] = None,
) -> ReliabilityMetrics:
    """Calculate reliability metrics for a single equipment unit."""
    close = conn is None
    if conn is None:
        conn = _pg(settings)
    try:
        now = datetime.utcnow()
        start = now - timedelta(days=window_days)
        failures = _query_failure_intervals(
            conn,
            equipment_filter="equipment_unit_id = %s",
            filter_params=(equipment_unit_id,),
            start=start,
        )
        return calculate_reliability(
            failures,
            observation_start=start,
            observation_end=now,
            equipment_unit_id=equipment_unit_id,
        )
    finally:
        if close:
            conn.close()


def get_asset_reliability(
    asset_id: str,
    *,
    window_days: int = 365,
    conn=None,
    settings: Optional[Settings] = None,
) -> ReliabilityMetrics:
    """Calculate reliability metrics for a legacy asset_id (backward compat)."""
    close = conn is None
    if conn is None:
        conn = _pg(settings)
    try:
        now = datetime.utcnow()
        start = now - timedelta(days=window_days)

        failures = _query_failure_intervals(
            conn,
            equipment_filter="asset_id = %s",
            filter_params=(asset_id,),
            start=start,
        )

        if not failures:
            failures = _query_legacy_failure_intervals(conn, asset_id, start)

        return calculate_reliability(
            failures,
            observation_start=start,
            observation_end=now,
            asset_id=asset_id,
        )
    finally:
        if close:
            conn.close()


def get_fleet_reliability(
    *,
    tenant_id: Optional[str] = None,
    iso_equipment_class: Optional[str] = None,
    equipment_family: Optional[str] = None,
    window_days: int = 365,
    conn=None,
    settings: Optional[Settings] = None,
) -> Dict[str, ReliabilityMetrics]:
    """Calculate reliability metrics grouped by equipment unit for a fleet.

    Filters by tenant, equipment class, or family.
    Returns: {equipment_unit_id: ReliabilityMetrics}
    """
    close = conn is None
    if conn is None:
        conn = _pg(settings)
    try:
        now = datetime.utcnow()
        start = now - timedelta(days=window_days)

        clauses = ["fe.failure_start_ts >= %s"]
        params: list = [start]

        if tenant_id:
            clauses.append("fe.tenant_id = %s")
            params.append(tenant_id)

        if iso_equipment_class or equipment_family:
            join = "JOIN equipment_units eu ON fe.equipment_unit_id = eu.equipment_unit_id"
            if iso_equipment_class:
                clauses.append("eu.iso_equipment_class = %s")
                params.append(iso_equipment_class)
            if equipment_family:
                clauses.append("eu.equipment_family = %s")
                params.append(equipment_family)
        else:
            join = ""

        where = " WHERE " + " AND ".join(clauses)

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT fe.event_id, fe.equipment_unit_id, fe.failure_start_ts,
                       fe.restoration_ts, fe.downtime_hours
                FROM failure_events fe
                {join}
                {where}
                ORDER BY fe.equipment_unit_id, fe.failure_start_ts
                """,
                params,
            )
            rows = cur.fetchall()

        grouped: Dict[str, List[FailureInterval]] = {}
        for event_id, equip_id, f_start, restoration, downtime in rows:
            if not equip_id or not f_start:
                continue
            grouped.setdefault(equip_id, []).append(
                FailureInterval(
                    event_id=event_id,
                    failure_start=f_start,
                    restoration=restoration,
                    downtime_hours=downtime,
                )
            )

        results = {}
        for equip_id, intervals in grouped.items():
            results[equip_id] = calculate_reliability(
                intervals,
                observation_start=start,
                observation_end=now,
                equipment_unit_id=equip_id,
            )

        return results
    finally:
        if close:
            conn.close()


def _query_failure_intervals(
    conn, equipment_filter: str, filter_params: tuple, start: datetime
) -> List[FailureInterval]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT event_id, failure_start_ts, restoration_ts, downtime_hours
            FROM failure_events
            WHERE {equipment_filter}
              AND failure_start_ts >= %s
            ORDER BY failure_start_ts
            """,
            (*filter_params, start),
        )
        return [
            FailureInterval(
                event_id=row[0],
                failure_start=row[1],
                restoration=row[2],
                downtime_hours=row[3],
            )
            for row in cur.fetchall()
            if row[1]
        ]


def _query_legacy_failure_intervals(
    conn, asset_id: str, start: datetime
) -> List[FailureInterval]:
    """Fallback: derive failure intervals from the legacy events table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_id, occurred_at
            FROM events
            WHERE asset_id = %s
              AND occurred_at >= %s
              AND kind IN ('alarm', 'anomaly')
            ORDER BY occurred_at
            """,
            (asset_id, start),
        )
        return [
            FailureInterval(event_id=row[0], failure_start=row[1])
            for row in cur.fetchall()
            if row[1]
        ]
