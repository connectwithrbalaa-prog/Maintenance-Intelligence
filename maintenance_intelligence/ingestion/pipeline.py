"""Ingestion pipeline — orchestrates adapter fetch → canonical → DB persist.

Usage:
  from maintenance_intelligence.ingestion.pipeline import run_ingestion
  result = run_ingestion("maximo")  # or "sap"
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psycopg2
from loguru import logger

from maintenance_intelligence.ingestion.base import (
    BaseIngestionAdapter,
    CanonicalEquipment,
    CanonicalFailureEvent,
    CanonicalWorkOrder,
    CanonicalSignal,
    IngestionResult,
)
from maintenance_intelligence.runner.config import Settings


def _create_adapter(source: str, settings: Settings) -> BaseIngestionAdapter:
    source = source.upper()
    if source == "SAP":
        from maintenance_intelligence.ingestion.sap_pm.adapter import SAPPMAdapter
        from maintenance_intelligence.ingestion.code_mapper import CodeMapper
        return SAPPMAdapter(
            base_url=settings.sap_base_url,
            client=settings.sap_client,
            api_key=settings.sap_api_key,
            plant=settings.sap_plant,
            tenant_id=settings.ingestion_tenant_id,
            code_mapper=CodeMapper(settings=settings),
        )
    if source == "MAXIMO":
        from maintenance_intelligence.ingestion.maximo.adapter import MaximoIngestionAdapter
        from maintenance_intelligence.ingestion.code_mapper import CodeMapper
        return MaximoIngestionAdapter(
            base_url=settings.maximo_base_url,
            api_key=settings.maximo_api_key,
            site_id=settings.maximo_site,
            tenant_id=settings.ingestion_tenant_id,
            timeout_s=settings.maximo_timeout_s,
            code_mapper=CodeMapper(settings=settings),
        )
    raise ValueError(f"Unknown source system: {source}")


def _persist_equipment(conn, items: list[CanonicalEquipment]) -> int:
    count = 0
    with conn.cursor() as cur:
        for e in items:
            try:
                cur.execute(
                    """INSERT INTO equipment_units (
                        equipment_unit_id, system_id, tag, iso_equipment_class,
                        equipment_family, oem_name, oem_model, criticality,
                        service_medium, duty_type, safety_critical, tenant_id, hierarchy_path
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (equipment_unit_id) DO UPDATE SET
                        tag = EXCLUDED.tag, iso_equipment_class = EXCLUDED.iso_equipment_class,
                        oem_name = EXCLUDED.oem_name, oem_model = EXCLUDED.oem_model,
                        criticality = EXCLUDED.criticality, updated_at = now()""",
                    (e.equipment_unit_id, e.system_id, e.tag, e.iso_equipment_class,
                     e.equipment_family, e.oem_name, e.oem_model, e.criticality,
                     e.service_medium, e.duty_type, e.safety_critical,
                     e.tenant_id, e.hierarchy_path),
                )
                count += 1
            except Exception as exc:
                logger.debug({"event": "persist.equipment.skip", "id": e.equipment_unit_id, "error": str(exc)})
    return count


def _persist_failure_events(conn, items: list[CanonicalFailureEvent]) -> int:
    count = 0
    with conn.cursor() as cur:
        for fe in items:
            try:
                cur.execute(
                    """INSERT INTO failure_events (
                        event_id, tenant_id, source_system, equipment_unit_id,
                        component_id, asset_id, failure_mode_code, failure_mechanism_code,
                        failure_cause_code, maintenance_action_code, detection_method_code,
                        consequence_code, impact_level, severity, kind, summary,
                        details, lineage, raw_source_ids,
                        failure_start_ts, restoration_ts, downtime_hours
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s)
                    ON CONFLICT (event_id) DO NOTHING""",
                    (fe.event_id, fe.tenant_id, fe.source_system,
                     fe.equipment_unit_id, fe.component_id, fe.asset_id,
                     fe.failure_mode_code, fe.failure_mechanism_code,
                     fe.failure_cause_code, fe.maintenance_action_code,
                     fe.detection_method_code, fe.consequence_code,
                     fe.impact_level, fe.severity, fe.kind, fe.summary,
                     json.dumps(fe.details) if fe.details else None,
                     json.dumps(fe.lineage) if fe.lineage else None,
                     json.dumps(fe.raw_source_ids) if fe.raw_source_ids else None,
                     fe.failure_start_ts, fe.restoration_ts, fe.downtime_hours),
                )
                count += 1
            except Exception as exc:
                logger.debug({"event": "persist.failure_event.skip", "id": fe.event_id, "error": str(exc)})
    return count


def _persist_work_orders(conn, items: list[CanonicalWorkOrder]) -> int:
    count = 0
    with conn.cursor() as cur:
        for wo in items:
            try:
                cur.execute(
                    """INSERT INTO workorders (
                        wo_id, asset_id, status, title, description, priority,
                        metadata, tenant_id
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                    ON CONFLICT (wo_id) DO UPDATE SET
                        status = EXCLUDED.status, title = EXCLUDED.title,
                        priority = EXCLUDED.priority""",
                    (wo.wo_id, wo.asset_id, wo.status, wo.title,
                     wo.description, wo.priority,
                     json.dumps({"source_system": wo.source_system,
                                 "maintenance_type": wo.maintenance_type,
                                 "raw_source_ids": wo.raw_source_ids}),
                     wo.tenant_id),
                )
                count += 1
            except Exception as exc:
                logger.debug({"event": "persist.work_order.skip", "id": wo.wo_id, "error": str(exc)})
    return count


def run_ingestion(
    source: str,
    *,
    settings: Optional[Settings] = None,
    page_size: int = 100,
) -> IngestionResult:
    """Run a full ingestion cycle for a source system.

    Fetches equipment, failure events, and work orders from the configured
    CMMS endpoint, normalizes to canonical schema, and persists to DB.
    """
    settings = settings or Settings()
    result = IngestionResult(
        source_system=source.upper(),
        adapter_name=source.lower(),
        started_at=datetime.now(timezone.utc),
    )

    try:
        adapter = _create_adapter(source, settings)
    except Exception as exc:
        result.error_count += 1
        result.errors.append(f"Adapter creation failed: {exc}")
        result.completed_at = datetime.now(timezone.utc)
        return result

    conn = psycopg2.connect(settings.pg_dsn)
    try:
        with conn:
            equipment = adapter.fetch_equipment(page_size=page_size)
            result.equipment_count = _persist_equipment(conn, equipment)

            failures = adapter.fetch_failure_events(page_size=page_size)
            result.failure_event_count = _persist_failure_events(conn, failures)

            work_orders = adapter.fetch_work_orders(page_size=page_size)
            result.work_order_count = _persist_work_orders(conn, work_orders)

        logger.info({
            "event": "ingestion.complete",
            "source": source,
            "equipment": result.equipment_count,
            "failures": result.failure_event_count,
            "work_orders": result.work_order_count,
        })
    except Exception as exc:
        result.error_count += 1
        result.errors.append(str(exc))
        logger.error({"event": "ingestion.error", "source": source, "error": str(exc)})
    finally:
        conn.close()

    result.completed_at = datetime.now(timezone.utc)
    return result
