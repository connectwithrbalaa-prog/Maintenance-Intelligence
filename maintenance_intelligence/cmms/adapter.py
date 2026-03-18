from __future__ import annotations

from abc import ABC, abstractmethod
import datetime as dt
import time
from typing import Any, Dict, Optional, Type

import httpx
from loguru import logger

from maintenance_intelligence.runner.config import Settings


TERMINAL_WORK_ORDER_STATUSES = {"COMP", "COMPLETE", "COMPLETED", "CLOSE", "CLOSED", "DONE"}
REGRESSIVE_WORK_ORDER_STATUSES = {"PENDING", "QUEUED", "DRAFT", "NEW"}


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


def _as_timestamp_text(value: Any) -> Optional[str]:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.isoformat()
    return _as_text(value)


def _first_timestamp(*values: Any) -> Optional[str]:
    for value in values:
        text = _as_timestamp_text(value)
        if text:
            return text
    return None


def _status_upper(status: Any) -> Optional[str]:
    text = _as_text(status)
    return text.upper() if text else None


def is_terminal_work_order_status(status: Any) -> bool:
    return (_status_upper(status) or "") in TERMINAL_WORK_ORDER_STATUSES


def work_order_lifecycle_phase(
    status: Any,
    handoff_completed_at: Any,
    workorder_completed_at: Any,
    *,
    workorder_created_at: Any = None,
    handoff_complete: Optional[bool] = None,
) -> str:
    if workorder_completed_at or is_terminal_work_order_status(status):
        return "completed"
    if handoff_completed_at:
        return "handoff-complete"
    if handoff_complete is False:
        return "pending"
    status_upper = _status_upper(status)
    if workorder_created_at or status_upper in REGRESSIVE_WORK_ORDER_STATUSES:
        return "created"
    if status_upper:
        return "active"
    return "pending"


def normalize_work_order_lifecycle(
    result: Any,
    *,
    status: Any = None,
    handoff_complete: Optional[bool] = None,
) -> Dict[str, Any]:
    payload = _as_dict(result)
    response_payload = _as_dict(payload.get("response"))
    raw_response = _as_dict(payload.get("raw_response")) or payload
    workorder_created_at = _first_timestamp(
        payload.get("workorder_created_at"),
        payload.get("created_at"),
        response_payload.get("workorder_created_at"),
        response_payload.get("created_at"),
        raw_response.get("workorder_created_at"),
        raw_response.get("created_at"),
    )
    normalized_status = _as_text(status if status is not None else payload.get("status")) or "PENDING"
    explicit_completed_at = _first_timestamp(
        payload.get("workorder_completed_at"),
        response_payload.get("workorder_completed_at"),
        response_payload.get("actfinish"),
        response_payload.get("completed_at"),
        response_payload.get("closed_at"),
        response_payload.get("finishdate"),
        raw_response.get("workorder_completed_at"),
        raw_response.get("actfinish"),
        raw_response.get("completed_at"),
        raw_response.get("closed_at"),
        raw_response.get("finishdate"),
    )
    if explicit_completed_at is None and is_terminal_work_order_status(normalized_status):
        explicit_completed_at = _first_timestamp(
            response_payload.get("statusdate"),
            response_payload.get("changedate"),
            raw_response.get("statusdate"),
            raw_response.get("changedate"),
        )
    if handoff_complete is not None:
        actual_handoff_complete = bool(handoff_complete)
    elif "handoff_complete" in payload:
        actual_handoff_complete = bool(payload.get("handoff_complete"))
    else:
        actual_handoff_complete = bool(payload.get("wo_id"))
    handoff_completed_at = _first_timestamp(
        payload.get("handoff_completed_at"),
        response_payload.get("handoff_completed_at"),
        raw_response.get("handoff_completed_at"),
        response_payload.get("statusdate"),
        response_payload.get("changedate"),
        raw_response.get("statusdate"),
        raw_response.get("changedate"),
        workorder_created_at if actual_handoff_complete else None,
    )
    if not actual_handoff_complete:
        handoff_completed_at = None
    phase = work_order_lifecycle_phase(
        normalized_status,
        handoff_completed_at,
        explicit_completed_at,
        workorder_created_at=workorder_created_at,
        handoff_complete=actual_handoff_complete,
    )
    return {
        "status": normalized_status,
        "status_upper": _status_upper(normalized_status) or "PENDING",
        "handoff_complete": actual_handoff_complete,
        "workorder_created_at": workorder_created_at,
        "handoff_completed_at": handoff_completed_at,
        "workorder_completed_at": explicit_completed_at,
        "terminal": bool(explicit_completed_at or is_terminal_work_order_status(normalized_status)),
        "phase": phase,
    }


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
    response_payload = _as_dict(result.get("response"))
    lifecycle = normalize_work_order_lifecycle(result)
    normalized = {
        "wo_id": _as_text(result.get("wo_id")),
        "status": lifecycle["status"],
        "backend": backend,
        "created_at": _as_text(result.get("created_at")),
        "request": _as_dict(result.get("request")),
        "response": response_payload,
        "raw_response": result,
        "message": _as_text(result.get("message")),
        "workorder_created_at": lifecycle["workorder_created_at"],
        "handoff_completed_at": lifecycle["handoff_completed_at"],
        "workorder_completed_at": lifecycle["workorder_completed_at"],
        "lifecycle_phase": lifecycle["phase"],
        "terminal_state": lifecycle["terminal"],
        "lifecycle": lifecycle,
    }
    normalized["handoff_complete"] = lifecycle["handoff_complete"]
    if not normalized["handoff_complete"]:
        normalized["handoff_completed_at"] = None
        normalized["lifecycle"] = {
            **lifecycle,
            "handoff_completed_at": None,
            "phase": work_order_lifecycle_phase(
                lifecycle["status"],
                None,
                lifecycle["workorder_completed_at"],
                workorder_created_at=lifecycle["workorder_created_at"],
                handoff_complete=False,
            ),
        }
        normalized["lifecycle_phase"] = normalized["lifecycle"]["phase"]
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
    backend_label = "Base"
    backend_description = "Base CMMS connector"
    config_fields: list[dict[str, Any]] = []

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def create_work_order(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """Create or stage a work order and return a normalized result payload."""

    @classmethod
    def describe_backend(cls, settings: Optional[Settings] = None) -> Dict[str, Any]:
        configured = True
        fields: list[dict[str, Any]] = []
        active_settings = settings or Settings()
        for field in cls.config_fields:
            field_name = _as_text(field.get("setting_name")) or ""
            env_var = _as_text(field.get("env_var")) or ""
            required = bool(field.get("required", False))
            value = getattr(active_settings, field_name, None) if field_name else None
            configured_value = bool(_as_text(value)) if value is not None else False
            if required and not configured_value:
                configured = False
            fields.append(
                {
                    "setting_name": field_name,
                    "env_var": env_var,
                    "required": required,
                    "secret": bool(field.get("secret", False)),
                    "default": field.get("default"),
                    "description": _as_text(field.get("description")) or "",
                    "configured": configured_value,
                }
            )
        return {
            "backend": cls.backend_name,
            "label": cls.backend_label,
            "description": cls.backend_description,
            "configured": configured,
            "config_fields": fields,
        }


def post_json_request(
    client: httpx.Client,
    *,
    endpoint: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    unavailable_detail: str,
):
    try:
        response = client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        raise CMMSUnavailableError(unavailable_detail) from exc


def parse_json_response_body(
    response: Any,
    *,
    invalid_json_detail: str,
    malformed_payload_detail: str,
    unwrap=None,
) -> Dict[str, Any]:
    try:
        body = response.json() if getattr(response, "content", None) else {}
    except ValueError as exc:
        raise CMMSPayloadError(invalid_json_detail) from exc
    if body is None:
        body = {}
    if unwrap is not None:
        body = unwrap(body)
    if not isinstance(body, dict):
        raise CMMSPayloadError(malformed_payload_detail)
    return body


def registered_cmms_adapters() -> Dict[str, Type[CMMSAdapter]]:
    from maintenance_intelligence.cmms.maximo import MaximoCMMSAdapter
    from maintenance_intelligence.cmms.mock import MockCMMSAdapter
    from maintenance_intelligence.cmms.sap_pm import SAPPMCMMSAdapter

    return {
        "mock": MockCMMSAdapter,
        "maximo": MaximoCMMSAdapter,
        "sap_pm": SAPPMCMMSAdapter,
    }


def supported_cmms_backends() -> list[str]:
    return sorted(registered_cmms_adapters())


def discover_cmms_backends(settings: Optional[Settings] = None) -> Dict[str, Any]:
    active_settings = settings or Settings()
    current_backend = _resolve_backend_name(getattr(active_settings, "pm_connector_backend", "mock"))
    adapters = registered_cmms_adapters()
    return {
        "current_backend": current_backend,
        "supported_backends": [
            adapter_cls.describe_backend(active_settings)
            for _backend, adapter_cls in sorted(adapters.items())
        ],
    }


def _resolve_backend_name(value: Any) -> str:
    normalized = (_as_text(value) or "mock").lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "sappm": "sap_pm",
    }
    return aliases.get(normalized, normalized)


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
    backend = _resolve_backend_name(getattr(settings, "pm_connector_backend", "mock"))
    adapters = registered_cmms_adapters()
    adapter_cls = adapters.get(backend)
    if adapter_cls is None:
        raise UnsupportedBackendError(
            f"Unsupported CMMS backend: {backend}. Supported backends: {', '.join(sorted(adapters))}"
        )
    return adapter_cls(settings)