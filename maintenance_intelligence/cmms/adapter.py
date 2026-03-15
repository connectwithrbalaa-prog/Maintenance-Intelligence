from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

from loguru import logger

from maintenance_intelligence.runner.config import Settings


class CMMSAdapterError(RuntimeError):
    pass


class UnsupportedBackendError(CMMSAdapterError):
    pass


class CMMSUnavailableError(CMMSAdapterError):
    pass


class CMMSPayloadError(CMMSAdapterError):
    pass


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def normalize_work_order_result(
    result: Any,
    *,
    recommendation: Dict[str, Any],
    backend_name: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(result, dict):
        logger.warning(
            "cmms.adapter.payload_malformed backend={} recommendation_id={} raw_payload={}",
            backend_name or "unknown",
            recommendation.get("id"),
            result,
        )
        raise CMMSPayloadError("CMMS backend returned malformed payload")

    backend = _as_text(result.get("backend")) or backend_name or "unknown"
    normalized = {
        "wo_id": _as_text(result.get("wo_id")),
        "status": _as_text(result.get("status")) or "PENDING",
        "backend": backend,
        "created_at": _as_text(result.get("created_at")),
        "request": _as_dict(result.get("request")),
        "response": _as_dict(result.get("response")),
        "raw_response": result,
        "message": _as_text(result.get("message")),
    }
    normalized["handoff_complete"] = bool(normalized["wo_id"])
    if not normalized["handoff_complete"]:
        logger.warning(
            "cmms.adapter.handoff_incomplete backend={} recommendation_id={} raw_payload={}",
            backend,
            recommendation.get("id"),
            result,
        )
    return normalized


class CMMSAdapter(ABC):
    backend_name = "base"

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def create_work_order(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """Create or stage a work order and return a normalized result payload."""


def create_cmms_adapter(settings: Settings) -> CMMSAdapter:
    from maintenance_intelligence.cmms.maximo import MaximoCMMSAdapter
    from maintenance_intelligence.cmms.mock import MockCMMSAdapter

    backend = getattr(settings, "pm_connector_backend", "mock").lower().strip()
    adapters: Dict[str, Type[CMMSAdapter]] = {
        "mock": MockCMMSAdapter,
        "maximo": MaximoCMMSAdapter,
    }
    adapter_cls = adapters.get(backend)
    if adapter_cls is None:
        raise UnsupportedBackendError(f"Unsupported CMMS backend: {backend}")
    return adapter_cls(settings)