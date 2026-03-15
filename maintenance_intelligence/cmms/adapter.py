from __future__ import annotations

from abc import ABC, abstractmethod
import datetime as dt
import time
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


class CMMSRetryExhaustedError(CMMSUnavailableError):
    def __init__(self, message: str, *, attempts: list[dict[str, Any]]):
        super().__init__(message)
        self.attempts = attempts


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


def _attempt_entry(
    *,
    attempt_number: int,
    handoff_state: str,
    connector_result: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "attempt_number": attempt_number,
        "attempted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "handoff_state": handoff_state,
        "result": "failure" if error_message else ("success" if handoff_state == "success" else "pending"),
        "connector_result": connector_result or {},
        "error_message": error_message or "",
    }


def submit_work_order_with_retry(
    adapter: CMMSAdapter,
    recommendation: Dict[str, Any],
    *,
    retry_attempts: int = 1,
    retry_interval_s: float = 0.0,
    sleep_fn=time.sleep,
) -> Dict[str, Any]:
    max_attempts = max(1, int(retry_attempts))
    attempts: list[dict[str, Any]] = []

    for attempt_number in range(1, max_attempts + 1):
        try:
            result = normalize_work_order_result(
                adapter.create_work_order(recommendation),
                recommendation=recommendation,
                backend_name=getattr(adapter, "backend_name", None),
            )
            handoff_state = "success" if result.get("handoff_complete") else "pending"
            attempts.append(
                _attempt_entry(
                    attempt_number=attempt_number,
                    handoff_state=handoff_state,
                    connector_result=result,
                )
            )
            return {**result, "_attempts": attempts}
        except CMMSPayloadError as exc:
            attempts.append(
                _attempt_entry(
                    attempt_number=attempt_number,
                    handoff_state="failure",
                    error_message=str(exc),
                )
            )
            exc.attempts = attempts
            raise
        except CMMSAdapterError as exc:
            if isinstance(exc, UnsupportedBackendError):
                raise
            attempts.append(
                _attempt_entry(
                    attempt_number=attempt_number,
                    handoff_state="failure",
                    error_message=str(exc),
                )
            )
            if attempt_number >= max_attempts:
                raise CMMSRetryExhaustedError(str(exc), attempts=attempts) from exc
            sleep_fn(max(0.0, float(retry_interval_s)))

    raise CMMSRetryExhaustedError("CMMS handoff retries exhausted", attempts=attempts)


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