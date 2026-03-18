from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _first_text(source: Dict[str, Any], fields: Iterable[str], fallback: Any = None) -> Optional[str]:
    for field in fields:
        text = _as_text(source.get(field))
        if text:
            return text
    return _as_text(fallback)


def translate_connector_response(
    body: Dict[str, Any],
    *,
    backend_name: str,
    recommendation: Dict[str, Any],
    wo_id_fields: Iterable[str],
    status_fields: Iterable[str],
    message_fields: Iterable[str] = (),
    workorder_created_fields: Iterable[str] = (),
    handoff_completed_fields: Iterable[str] = (),
    workorder_completed_fields: Iterable[str] = (),
    default_status: str = "PENDING",
) -> Dict[str, Any]:
    return {
        "wo_id": _first_text(body, wo_id_fields, recommendation.get("id")),
        "status": _first_text(body, status_fields, default_status) or default_status,
        "backend": backend_name,
        "response": body,
        "message": _first_text(body, message_fields),
        "workorder_created_at": _first_text(body, workorder_created_fields),
        "handoff_completed_at": _first_text(body, handoff_completed_fields),
        "workorder_completed_at": _first_text(body, workorder_completed_fields),
    }