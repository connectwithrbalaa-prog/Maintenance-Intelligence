from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from maintenance_intelligence.runner.config import Settings


SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _utcnow_text() -> str:
    return _utcnow().isoformat()


def _notification_log_path(settings: Settings) -> Path:
    return Path(settings.notification_log_path).expanduser()


def _parse_routes(settings: Settings) -> Dict[str, Dict[str, Any]]:
    raw = settings.notification_webhook_routes
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}

    routes: Dict[str, Dict[str, Any]] = {}
    for route_key, route_value in parsed.items():
        route_name = _as_text(route_key)
        if route_name is None:
            continue
        if isinstance(route_value, str):
            route = {"webhook_url": route_value}
        elif isinstance(route_value, dict):
            route = route_value
        else:
            continue
        webhook_url = _as_text(route.get("webhook_url"))
        if webhook_url is None:
            continue
        minimum_severity = (_as_text(route.get("minimum_severity")) or "warning").lower()
        if minimum_severity not in SEVERITY_ORDER:
            minimum_severity = "warning"
        routes[route_name] = {
            "route_id": route_name,
            "webhook_url": webhook_url,
            "minimum_severity": minimum_severity,
        }
    return routes


def _severity_value(value: str) -> int:
    return SEVERITY_ORDER.get(value.lower(), SEVERITY_ORDER["warning"])


def _resolve_route(settings: Settings, *, org_id: Optional[str], severity: str) -> Optional[Dict[str, Any]]:
    routes = _parse_routes(settings)
    candidates: List[str] = []
    org_key = _as_text(org_id)
    if org_key:
        candidates.append(org_key)
    candidates.append("default")
    for route_key in candidates:
        route = routes.get(route_key)
        if not route:
            continue
        if _severity_value(severity) < _severity_value(route.get("minimum_severity", "warning")):
            return None
        return route
    return None


def _load_records(settings: Settings) -> List[Dict[str, Any]]:
    path = _notification_log_path(settings)
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    parsed = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(parsed, dict):
                    records.append(parsed)
    except OSError:
        return []
    return records


def _persist_record(settings: Settings, record: Dict[str, Any]) -> None:
    path = _notification_log_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _parsed_attempted_at(record: Dict[str, Any]) -> Optional[dt.datetime]:
    attempted_at = _as_text(record.get("attempted_at"))
    if attempted_at is None:
        return None
    try:
        return dt.datetime.fromisoformat(attempted_at)
    except ValueError:
        return None


def _find_duplicate(settings: Settings, *, dedupe_key: Optional[str]) -> Optional[Dict[str, Any]]:
    key = _as_text(dedupe_key)
    if key is None:
        return None
    cutoff = _utcnow() - dt.timedelta(seconds=max(0, int(settings.notification_dedupe_window_s)))
    for record in reversed(_load_records(settings)):
        if _as_text(record.get("dedupe_key")) != key:
            continue
        attempted_at = _parsed_attempted_at(record)
        if attempted_at is None or attempted_at < cutoff:
            return None
        return record
    return None


def _destination_label(url: Optional[str]) -> str:
    if not url:
        return "unconfigured"
    parsed = urlparse(url)
    return parsed.netloc or parsed.path or "webhook"


def _matches_filter(record_value: Any, filter_value: Optional[str]) -> bool:
    normalized_filter = (_as_text(filter_value) or "").strip().lower()
    if not normalized_filter or normalized_filter == "all":
        return True
    normalized_record = (_as_text(record_value) or "").strip().lower()
    return normalized_record == normalized_filter


def _send_webhook(url: str, payload: Dict[str, Any], timeout_s: float) -> tuple[bool, Optional[int], str]:
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(url, json=payload)
        if 200 <= response.status_code < 300:
            return True, response.status_code, ""
        return False, response.status_code, f"Webhook returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        return False, None, str(exc)


def emit_notification(
    *,
    event_type: str,
    severity: str,
    summary: str,
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    dedupe_key: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    settings = settings or Settings()
    duplicate = _find_duplicate(settings, dedupe_key=dedupe_key)
    if duplicate is not None:
        return duplicate

    normalized_severity = (_as_text(severity) or "warning").lower()
    if normalized_severity not in SEVERITY_ORDER:
        normalized_severity = "warning"
    route = _resolve_route(settings, org_id=org_id, severity=normalized_severity)
    webhook_url = _as_text(route.get("webhook_url")) if route else None
    route_id = _as_text(route.get("route_id")) if route else None
    attempted_at = _utcnow_text()
    record = {
        "attempted_at": attempted_at,
        "delivered_at": None,
        "channel": "webhook",
        "status": "skipped",
        "event_type": _as_text(event_type) or "unknown",
        "severity": normalized_severity,
        "summary": _as_text(summary) or "",
        "org_id": _as_text(org_id) or "",
        "site_id": _as_text(site_id) or "",
        "route_id": route_id or "",
        "destination": _destination_label(webhook_url),
        "dedupe_key": _as_text(dedupe_key) or "",
        "response_status_code": None,
        "delivery_error": "",
        "payload": payload if isinstance(payload, dict) else {},
    }
    if not webhook_url:
        record["delivery_error"] = "No webhook route configured"
        _persist_record(settings, record)
        return record

    delivered, status_code, error = _send_webhook(
        webhook_url,
        {
            "event_type": record["event_type"],
            "severity": record["severity"],
            "summary": record["summary"],
            "org_id": record["org_id"],
            "site_id": record["site_id"],
            "occurred_at": attempted_at,
            "payload": record["payload"],
        },
        settings.notification_webhook_timeout_s,
    )
    record["response_status_code"] = status_code
    if delivered:
        record["status"] = "sent"
        record["delivered_at"] = attempted_at
    else:
        record["status"] = "failed"
        record["delivery_error"] = error
    _persist_record(settings, record)
    return record


def recent_notification_deliveries(
    *,
    limit: int = 6,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    event_type: Optional[str] = None,
    destination: Optional[str] = None,
    prioritize_failures: bool = True,
    settings: Optional[Settings] = None,
) -> List[Dict[str, Any]]:
    settings = settings or Settings()
    records = _load_records(settings)
    filtered = [
        record
        for record in records
        if isinstance(record, dict)
        and _matches_filter(record.get("status"), status)
        and _matches_filter(record.get("severity"), severity)
        and _matches_filter(record.get("event_type"), event_type)
        and _matches_filter(record.get("destination"), destination)
    ]

    ordered_by_time = sorted(filtered, key=lambda record: _as_text(record.get("attempted_at")) or "", reverse=True)
    if prioritize_failures:
        failed = [record for record in ordered_by_time if (_as_text(record.get("status")) or "").lower() == "failed"]
        non_failed = [record for record in ordered_by_time if (_as_text(record.get("status")) or "").lower() != "failed"]
        ordered = failed + non_failed
    else:
        ordered = ordered_by_time
    return ordered[:max(1, int(limit))]