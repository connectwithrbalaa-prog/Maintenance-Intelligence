"""API router for CMMS connector management.

Endpoints:
  GET  /api/v1/connectors/status      — status of all configured connectors
  POST /api/v1/connectors/test/{source} — test connectivity to a source
  POST /api/v1/connectors/sync/{source} — trigger ingestion from a source
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request
from loguru import logger

from maintenance_intelligence.api.middleware.identity import (
    require_authenticated_identity,
)
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


def _adapter_status(settings: Settings) -> Dict[str, Any]:
    return {
        "sap_pm": {
            "configured": bool(settings.sap_base_url),
            "base_url": settings.sap_base_url or "not set",
            "plant": settings.sap_plant or "not set",
        },
        "maximo": {
            "configured": bool(settings.maximo_base_url),
            "base_url": settings.maximo_base_url or "not set",
            "site": settings.maximo_site,
        },
        "tenant_id": settings.ingestion_tenant_id,
    }


@router.get("/status")
def connector_status(request: Request):
    require_authenticated_identity(
        request, detail="Connector status requires an authenticated identity"
    )
    settings = Settings()
    return _adapter_status(settings)


@router.post("/test/{source}")
def test_connector(request: Request, source: str):
    """Test connectivity to a CMMS source (sap or maximo)."""
    require_authenticated_identity(
        request, detail="Connector testing requires an authenticated identity"
    )
    settings = Settings()
    source_upper = source.upper()
    try:
        if source_upper == "SAP":
            from maintenance_intelligence.ingestion.sap_pm.adapter import SAPPMAdapter
            adapter = SAPPMAdapter(
                base_url=settings.sap_base_url, client=settings.sap_client,
                api_key=settings.sap_api_key, plant=settings.sap_plant,
            )
        elif source_upper == "MAXIMO":
            from maintenance_intelligence.ingestion.maximo.adapter import MaximoIngestionAdapter
            adapter = MaximoIngestionAdapter(
                base_url=settings.maximo_base_url, api_key=settings.maximo_api_key,
                site_id=settings.maximo_site, timeout_s=settings.maximo_timeout_s,
            )
        else:
            return {"status": "error", "detail": f"Unknown source: {source}"}
        return adapter.test_connection()
    except Exception as exc:
        return {"status": "error", "adapter": source, "error": str(exc)}


@router.post("/sync/{source}")
def sync_connector(request: Request, source: str):
    """Trigger a full ingestion cycle from a CMMS source."""
    require_authenticated_identity(
        request, detail="Connector sync requires an authenticated identity"
    )
    settings = Settings()
    try:
        from maintenance_intelligence.ingestion.pipeline import run_ingestion
        result = run_ingestion(source, settings=settings, page_size=settings.ingestion_page_size)
        return {
            "status": "ok" if result.success else "error",
            "source": result.source_system,
            "equipment_synced": result.equipment_count,
            "failure_events_synced": result.failure_event_count,
            "work_orders_synced": result.work_order_count,
            "errors": result.errors,
            "started_at": result.started_at.isoformat() if result.started_at else None,
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
        }
    except Exception as exc:
        logger.error({"event": "connector.sync.error", "source": source, "error": str(exc)})
        return {"status": "error", "source": source, "error": str(exc)}
