"""Structured retrievers for ISO 14224–aligned RCA context.

These replace ad-hoc SQL queries with typed retrieval functions that
return domain-specific context for GenAI prompts:

  get_hierarchy_context(equipment_unit_id)
    → full L1–L8 path + equipment attributes

  get_failure_history(equipment_unit_id, window_days)
    → past ISO-coded failure events for this equipment

  get_iso_taxonomy_context(failure_mode_code)
    → ISO 14224 reference data for the detected failure mode

  get_similar_equipment_failures(iso_equipment_class, failure_mode_code)
    → fleet-wide failures on similar equipment for cross-reference

  get_equipment_reliability_context(equipment_unit_id)
    → MTBF, MTTR, availability for prompt enrichment
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psycopg2

from maintenance_intelligence.runner.config import Settings


@dataclass
class HierarchyContext:
    """Full hierarchy path and equipment attributes for RCA context."""

    equipment_unit_id: str
    tag: str = ""
    iso_equipment_class: str = ""
    equipment_family: Optional[str] = None
    criticality: Optional[str] = None
    service_medium: Optional[str] = None
    oem_name: Optional[str] = None
    oem_model: Optional[str] = None
    safety_critical: bool = False
    system_name: Optional[str] = None
    system_type: Optional[str] = None
    system_group: Optional[str] = None
    facility_name: Optional[str] = None
    facility_type: Optional[str] = None
    site_name: Optional[str] = None
    basin_region: Optional[str] = None
    bu_name: Optional[str] = None
    industry_name: Optional[str] = None

    def to_prompt_text(self) -> str:
        lines = [
            f"Equipment: {self.tag} ({self.iso_equipment_class})",
            f"System: {self.system_name} ({self.system_type}, {self.system_group})" if self.system_name else "",
            f"Facility: {self.facility_name} ({self.facility_type})" if self.facility_name else "",
            f"Site: {self.site_name}, {self.basin_region}" if self.site_name else "",
            f"Criticality: {self.criticality}" if self.criticality else "",
            f"Service medium: {self.service_medium}" if self.service_medium else "",
            f"OEM: {self.oem_name} {self.oem_model}" if self.oem_name else "",
            f"Safety critical: {'Yes' if self.safety_critical else 'No'}",
        ]
        return "\n".join(line for line in lines if line)


@dataclass
class FailureHistoryEntry:
    """A past failure event for context."""

    event_id: str
    failure_mode_code: Optional[str] = None
    failure_mechanism_code: Optional[str] = None
    failure_cause_code: Optional[str] = None
    maintenance_action_code: Optional[str] = None
    summary: Optional[str] = None
    failure_start_ts: Optional[datetime] = None
    downtime_hours: Optional[float] = None
    severity: Optional[str] = None


@dataclass
class ISOTaxonomyContext:
    """ISO 14224 reference data for a failure classification."""

    failure_mode: Optional[Dict[str, str]] = None
    failure_mechanism: Optional[Dict[str, str]] = None
    failure_cause: Optional[Dict[str, str]] = None
    maintenance_action: Optional[Dict[str, str]] = None
    detection_method: Optional[Dict[str, str]] = None

    def to_prompt_text(self) -> str:
        lines = []
        if self.failure_mode:
            lines.append(f"ISO failure mode: {self.failure_mode.get('code', '')} — {self.failure_mode.get('name', '')} ({self.failure_mode.get('description', '')})")
        if self.failure_mechanism:
            lines.append(f"ISO failure mechanism: {self.failure_mechanism.get('code', '')} — {self.failure_mechanism.get('name', '')} ({self.failure_mechanism.get('description', '')})")
        if self.failure_cause:
            lines.append(f"ISO failure cause: {self.failure_cause.get('code', '')} — {self.failure_cause.get('name', '')} ({self.failure_cause.get('description', '')})")
        if self.maintenance_action:
            lines.append(f"ISO maintenance action: {self.maintenance_action.get('code', '')} — {self.maintenance_action.get('name', '')} ({self.maintenance_action.get('description', '')})")
        return "\n".join(lines) if lines else "No ISO taxonomy context available."


@dataclass
class RCAContext:
    """Assembled context for a GenAI RCA prompt."""

    hierarchy: Optional[HierarchyContext] = None
    failure_history: List[FailureHistoryEntry] = field(default_factory=list)
    iso_taxonomy: Optional[ISOTaxonomyContext] = None
    similar_failures: List[FailureHistoryEntry] = field(default_factory=list)
    reliability_summary: Optional[Dict[str, Any]] = None
    doc_chunks: List[Dict[str, str]] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        sections = []
        if self.hierarchy:
            sections.append(f"## Equipment context\n{self.hierarchy.to_prompt_text()}")
        if self.iso_taxonomy:
            sections.append(f"## ISO 14224 taxonomy\n{self.iso_taxonomy.to_prompt_text()}")
        if self.failure_history:
            history_lines = [f"- [{e.failure_mode_code or '?'}] {e.summary or 'No summary'} (downtime: {e.downtime_hours or '?'}h)" for e in self.failure_history[:10]]
            sections.append(f"## Past failures on this equipment ({len(self.failure_history)} total)\n" + "\n".join(history_lines))
        if self.similar_failures:
            sim_lines = [f"- [{e.failure_mode_code or '?'}] {e.summary or 'No summary'}" for e in self.similar_failures[:5]]
            sections.append(f"## Similar failures on fleet equipment\n" + "\n".join(sim_lines))
        if self.reliability_summary:
            r = self.reliability_summary
            sections.append(f"## Reliability metrics\nMTBF: {r.get('mtbf_hours', 'N/A')}h | MTTR: {r.get('mttr_hours', 'N/A')}h | Availability: {r.get('availability', 'N/A')}")
        if self.doc_chunks:
            chunks = [f"- {c.get('title', 'Untitled')}: {c.get('content', '')[:200]}" for c in self.doc_chunks[:5]]
            sections.append(f"## Reference documents\n" + "\n".join(chunks))
        return "\n\n".join(sections) if sections else "No structured context available."


def _pg(settings: Optional[Settings] = None):
    s = settings or Settings()
    return psycopg2.connect(s.pg_dsn)


def _row_dict(cur) -> Optional[Dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def _rows_dict(cur) -> List[Dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_hierarchy_context(
    equipment_unit_id: str, *, conn=None, settings: Optional[Settings] = None
) -> Optional[HierarchyContext]:
    """Retrieve the full ISO 14224 hierarchy path for an equipment unit."""
    close = conn is None
    if conn is None:
        conn = _pg(settings)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.equipment_unit_id, e.tag, e.iso_equipment_class, e.equipment_family,
                       e.criticality, e.service_medium, e.oem_name, e.oem_model, e.safety_critical,
                       s.name AS system_name, s.system_type, s.system_group,
                       f.name AS facility_name, f.facility_type,
                       si.name AS site_name, si.basin_region,
                       bu.name AS bu_name, ind.name AS industry_name
                FROM equipment_units e
                JOIN systems s ON e.system_id = s.system_id
                JOIN facilities f ON s.facility_id = f.facility_id
                JOIN sites si ON f.site_id = si.site_id
                JOIN business_units bu ON si.bu_code = bu.bu_code
                JOIN industries ind ON bu.industry_code = ind.industry_code
                WHERE e.equipment_unit_id = %s
                """,
                (equipment_unit_id,),
            )
            row = _row_dict(cur)
            if not row:
                return None
            return HierarchyContext(**{k: v for k, v in row.items() if k in HierarchyContext.__dataclass_fields__})
    finally:
        if close:
            conn.close()


def get_failure_history(
    equipment_unit_id: str,
    *,
    window_days: int = 365,
    limit: int = 20,
    conn=None,
    settings: Optional[Settings] = None,
) -> List[FailureHistoryEntry]:
    """Retrieve past ISO-coded failure events for an equipment unit."""
    close = conn is None
    if conn is None:
        conn = _pg(settings)
    try:
        start = datetime.utcnow() - timedelta(days=window_days)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_id, failure_mode_code, failure_mechanism_code,
                       failure_cause_code, maintenance_action_code,
                       summary, failure_start_ts, downtime_hours, severity
                FROM failure_events
                WHERE equipment_unit_id = %s AND failure_start_ts >= %s
                ORDER BY failure_start_ts DESC
                LIMIT %s
                """,
                (equipment_unit_id, start, limit),
            )
            return [
                FailureHistoryEntry(
                    event_id=r["event_id"],
                    failure_mode_code=r.get("failure_mode_code"),
                    failure_mechanism_code=r.get("failure_mechanism_code"),
                    failure_cause_code=r.get("failure_cause_code"),
                    maintenance_action_code=r.get("maintenance_action_code"),
                    summary=r.get("summary"),
                    failure_start_ts=r.get("failure_start_ts"),
                    downtime_hours=r.get("downtime_hours"),
                    severity=r.get("severity"),
                )
                for r in _rows_dict(cur)
            ]
    finally:
        if close:
            conn.close()


def get_iso_taxonomy_context(
    *,
    failure_mode_code: Optional[str] = None,
    failure_mechanism_code: Optional[str] = None,
    failure_cause_code: Optional[str] = None,
    maintenance_action_code: Optional[str] = None,
    detection_method_code: Optional[str] = None,
    conn=None,
    settings: Optional[Settings] = None,
) -> ISOTaxonomyContext:
    """Look up ISO 14224 reference data for given classification codes."""
    close = conn is None
    if conn is None:
        conn = _pg(settings)
    try:
        ctx = ISOTaxonomyContext()
        with conn.cursor() as cur:
            if failure_mode_code:
                cur.execute("SELECT code, name, description FROM iso_failure_modes WHERE code = %s", (failure_mode_code.upper(),))
                ctx.failure_mode = _row_dict(cur)
            if failure_mechanism_code:
                cur.execute("SELECT code, name, description FROM iso_failure_mechanisms WHERE code = %s", (failure_mechanism_code.upper(),))
                ctx.failure_mechanism = _row_dict(cur)
            if failure_cause_code:
                cur.execute("SELECT code, name, description FROM iso_failure_causes WHERE code = %s", (failure_cause_code.upper(),))
                ctx.failure_cause = _row_dict(cur)
            if maintenance_action_code:
                cur.execute("SELECT code, name, description FROM iso_maintenance_actions WHERE code = %s", (maintenance_action_code.upper(),))
                ctx.maintenance_action = _row_dict(cur)
            if detection_method_code:
                cur.execute("SELECT code, name, description FROM iso_detection_methods WHERE code = %s", (detection_method_code.upper(),))
                ctx.detection_method = _row_dict(cur)
        return ctx
    finally:
        if close:
            conn.close()


def get_similar_equipment_failures(
    iso_equipment_class: str,
    failure_mode_code: Optional[str] = None,
    *,
    exclude_equipment_id: Optional[str] = None,
    window_days: int = 365,
    limit: int = 10,
    conn=None,
    settings: Optional[Settings] = None,
) -> List[FailureHistoryEntry]:
    """Find failures on similar equipment across the fleet for cross-reference."""
    close = conn is None
    if conn is None:
        conn = _pg(settings)
    try:
        start = datetime.utcnow() - timedelta(days=window_days)
        clauses = ["eu.iso_equipment_class = %s", "fe.failure_start_ts >= %s"]
        params: list = [iso_equipment_class.upper(), start]
        if failure_mode_code:
            clauses.append("fe.failure_mode_code = %s")
            params.append(failure_mode_code.upper())
        if exclude_equipment_id:
            clauses.append("fe.equipment_unit_id != %s")
            params.append(exclude_equipment_id)
        params.append(limit)
        where = " AND ".join(clauses)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT fe.event_id, fe.failure_mode_code, fe.failure_mechanism_code,
                       fe.failure_cause_code, fe.maintenance_action_code,
                       fe.summary, fe.failure_start_ts, fe.downtime_hours, fe.severity
                FROM failure_events fe
                JOIN equipment_units eu ON fe.equipment_unit_id = eu.equipment_unit_id
                WHERE {where}
                ORDER BY fe.failure_start_ts DESC
                LIMIT %s
                """,
                params,
            )
            return [
                FailureHistoryEntry(
                    event_id=r["event_id"],
                    failure_mode_code=r.get("failure_mode_code"),
                    failure_mechanism_code=r.get("failure_mechanism_code"),
                    failure_cause_code=r.get("failure_cause_code"),
                    maintenance_action_code=r.get("maintenance_action_code"),
                    summary=r.get("summary"),
                    failure_start_ts=r.get("failure_start_ts"),
                    downtime_hours=r.get("downtime_hours"),
                    severity=r.get("severity"),
                )
                for r in _rows_dict(cur)
            ]
    finally:
        if close:
            conn.close()


def assemble_rca_context(
    equipment_unit_id: str,
    *,
    failure_mode_code: Optional[str] = None,
    failure_mechanism_code: Optional[str] = None,
    failure_cause_code: Optional[str] = None,
    window_days: int = 365,
    conn=None,
    settings: Optional[Settings] = None,
) -> RCAContext:
    """Assemble complete structured context for a GenAI RCA prompt.

    Combines hierarchy, failure history, ISO taxonomy, similar failures,
    and reliability metrics into a single context object.
    """
    close = conn is None
    if conn is None:
        conn = _pg(settings)
    try:
        hierarchy = get_hierarchy_context(equipment_unit_id, conn=conn)

        failure_history = get_failure_history(
            equipment_unit_id, window_days=window_days, conn=conn
        )

        iso_taxonomy = get_iso_taxonomy_context(
            failure_mode_code=failure_mode_code,
            failure_mechanism_code=failure_mechanism_code,
            failure_cause_code=failure_cause_code,
            conn=conn,
        )

        similar = []
        if hierarchy and hierarchy.iso_equipment_class:
            similar = get_similar_equipment_failures(
                hierarchy.iso_equipment_class,
                failure_mode_code=failure_mode_code,
                exclude_equipment_id=equipment_unit_id,
                window_days=window_days,
                conn=conn,
            )

        from maintenance_intelligence.core.reliability.queries import get_equipment_reliability
        reliability = get_equipment_reliability(
            equipment_unit_id, window_days=window_days, conn=conn
        )

        return RCAContext(
            hierarchy=hierarchy,
            failure_history=failure_history,
            iso_taxonomy=iso_taxonomy,
            similar_failures=similar,
            reliability_summary=reliability.to_dict() if reliability else None,
        )
    finally:
        if close:
            conn.close()
