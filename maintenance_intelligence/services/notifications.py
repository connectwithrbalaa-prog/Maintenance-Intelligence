from __future__ import annotations

import datetime as dt
import json
import smtplib
from email.message import EmailMessage
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


def _as_text_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        items: List[str] = []
        for item in value:
            text = _as_text(item)
            if text is not None:
                items.append(text)
        return items
    text = _as_text(value)
    return [text] if text is not None else []


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _utcnow_text() -> str:
    return _utcnow().isoformat()


def _notification_log_path(settings: Settings) -> Path:
    return Path(settings.notification_log_path).expanduser()


def _normalize_severity(value: Any, *, default: str = "warning") -> str:
    normalized = (_as_text(value) or default).strip().lower()
    return normalized if normalized in SEVERITY_ORDER else default


def _normalize_severity_list(value: Any) -> List[str]:
    items = []
    for item in _as_text_list(value):
        normalized = _normalize_severity(item, default="")
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _normalize_email_list(value: Any) -> List[str]:
    candidates = _as_text_list(value)
    recipients: List[str] = []
    for candidate in candidates:
        normalized = candidate.strip().lower()
        if "@" not in normalized:
            continue
        if normalized not in recipients:
            recipients.append(normalized)
    return recipients


def _coerce_route(
    route_id_hint: Optional[str], route_value: Any, *, index: int
) -> Optional[Dict[str, Any]]:
    if isinstance(route_value, str):
        route = {"webhook_url": route_value}
    elif isinstance(route_value, dict):
        route = route_value
    else:
        return None

    webhook_url = _as_text(route.get("webhook_url"))
    email_to = _normalize_email_list(route.get("email_to") or route.get("email"))
    if webhook_url is None and not email_to:
        return None

    route_id = _as_text(route.get("route_id")) or route_id_hint or f"route-{index}"
    org_ids = _as_text_list(route.get("org_ids") or route.get("org_id"))
    site_ids = _as_text_list(route.get("site_ids") or route.get("site_id"))
    event_types = _as_text_list(route.get("event_types") or route.get("event_type"))
    severities = _normalize_severity_list(route.get("severities") or route.get("severity"))

    if (
        route_id_hint
        and route_id_hint != "default"
        and not org_ids
        and "org_ids" not in route
        and "org_id" not in route
    ):
        org_ids = [route_id_hint]

    priority = route.get("priority", 0)
    try:
        normalized_priority = int(priority)
    except (TypeError, ValueError):
        normalized_priority = 0

    return {
        "route_id": route_id,
        "webhook_url": webhook_url,
        "email_to": email_to,
        "minimum_severity": _normalize_severity(route.get("minimum_severity")),
        "org_ids": org_ids,
        "site_ids": site_ids,
        "event_types": event_types,
        "severities": severities,
        "priority": normalized_priority,
    }


def _parse_routes(settings: Settings) -> List[Dict[str, Any]]:
    raw = settings.notification_webhook_routes
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []

    route_entries: List[tuple[Optional[str], Any]] = []
    if isinstance(parsed, dict):
        if isinstance(parsed.get("routes"), list):
            route_entries.extend((None, value) for value in parsed.get("routes") or [])
        else:
            for route_key, route_value in parsed.items():
                route_name = _as_text(route_key)
                if route_name is None:
                    continue
                if isinstance(route_value, list):
                    for value in route_value:
                        route_entries.append((route_name, value))
                else:
                    route_entries.append((route_name, route_value))
    elif isinstance(parsed, list):
        route_entries.extend((None, value) for value in parsed)
    else:
        return []

    routes: List[Dict[str, Any]] = []
    for index, (route_id_hint, route_value) in enumerate(route_entries, start=1):
        route = _coerce_route(route_id_hint, route_value, index=index)
        if route is not None:
            routes.append(route)
    return routes


def _severity_value(value: str) -> int:
    return SEVERITY_ORDER.get(value.lower(), SEVERITY_ORDER["warning"])


def _normalize_route_summary(route: Dict[str, Any]) -> Dict[str, Any]:
    webhook_url = _as_text(route.get("webhook_url"))
    email_to = _normalize_email_list(route.get("email_to"))
    destination = _destination_label(webhook_url)
    if not webhook_url and email_to:
        destination = ",".join(email_to)
    return {
        "route_id": _as_text(route.get("route_id")) or "",
        "destination": destination,
        "channels": [
            channel
            for channel, enabled in (("webhook", bool(webhook_url)), ("email", bool(email_to)))
            if enabled
        ],
        "email_to": email_to,
        "minimum_severity": _normalize_severity(route.get("minimum_severity")),
        "org_ids": list(route.get("org_ids") or []),
        "site_ids": list(route.get("site_ids") or []),
        "event_types": list(route.get("event_types") or []),
        "severities": list(route.get("severities") or []),
        "priority": int(route.get("priority", 0) or 0),
        "specificity": _route_specificity(route),
    }


def _route_evaluation(
    route: Dict[str, Any],
    *,
    org_id: Optional[str],
    site_id: Optional[str],
    event_type: str,
    severity: str,
) -> Dict[str, Any]:
    normalized_route = _normalize_route_summary(route)
    reasons: List[str] = []
    normalized_severity = _normalize_severity(severity)
    minimum_severity = normalized_route["minimum_severity"]
    explicit_severities = normalized_route["severities"]
    org_key = _as_text(org_id)
    site_key = _as_text(site_id)
    event_key = _as_text(event_type)

    if _severity_value(normalized_severity) < _severity_value(minimum_severity):
        reasons.append("severity_below_minimum")
    if explicit_severities and normalized_severity not in explicit_severities:
        reasons.append("severity_not_allowed")
    if normalized_route["org_ids"] and org_key not in normalized_route["org_ids"]:
        reasons.append("org_mismatch")
    if normalized_route["site_ids"] and site_key not in normalized_route["site_ids"]:
        reasons.append("site_mismatch")
    if normalized_route["event_types"] and event_key not in normalized_route["event_types"]:
        reasons.append("event_type_mismatch")

    return {
        **normalized_route,
        "matched": not reasons,
        "selected": False,
        "reasons": reasons,
    }


def _route_matches(
    route: Dict[str, Any],
    *,
    org_id: Optional[str],
    site_id: Optional[str],
    event_type: str,
    severity: str,
) -> bool:
    normalized_severity = _normalize_severity(severity)
    if _severity_value(normalized_severity) < _severity_value(
        route.get("minimum_severity", "warning")
    ):
        return False

    explicit_severities = route.get("severities") or []
    if explicit_severities and normalized_severity not in explicit_severities:
        return False

    org_key = _as_text(org_id)
    site_key = _as_text(site_id)
    event_key = _as_text(event_type)

    if route.get("org_ids") and org_key not in route["org_ids"]:
        return False
    if route.get("site_ids") and site_key not in route["site_ids"]:
        return False
    if route.get("event_types") and event_key not in route["event_types"]:
        return False
    return True


def _route_specificity(route: Dict[str, Any]) -> int:
    specificity = 0
    if route.get("org_ids"):
        specificity += 1
    if route.get("site_ids"):
        specificity += 1
    if route.get("event_types"):
        specificity += 1
    if route.get("severities"):
        specificity += 1
    return specificity


def _resolve_routes(
    settings: Settings,
    *,
    org_id: Optional[str],
    site_id: Optional[str],
    event_type: str,
    severity: str,
) -> List[Dict[str, Any]]:
    routes = _parse_routes(settings)
    matching = [
        route
        for route in routes
        if _route_matches(
            route, org_id=org_id, site_id=site_id, event_type=event_type, severity=severity
        )
    ]
    if not matching:
        return []

    best_specificity = max(_route_specificity(route) for route in matching)
    most_specific = [route for route in matching if _route_specificity(route) == best_specificity]
    best_priority = max(int(route.get("priority", 0)) for route in most_specific)
    selected = [route for route in most_specific if int(route.get("priority", 0)) == best_priority]
    return sorted(selected, key=lambda route: _as_text(route.get("route_id")) or "")


def list_notification_routes(*, settings: Optional[Settings] = None) -> List[Dict[str, Any]]:
    settings = settings or Settings()
    routes = [_normalize_route_summary(route) for route in _parse_routes(settings)]
    return sorted(
        routes,
        key=lambda route: (
            -(int(route.get("specificity") or 0)),
            -(int(route.get("priority") or 0)),
            route.get("route_id") or "",
        ),
    )


def preview_notification_routes(
    *,
    event_type: str,
    severity: str,
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    settings = settings or Settings()
    normalized_event_type = _as_text(event_type) or "unknown"
    normalized_severity = _normalize_severity(severity)
    routes = _parse_routes(settings)
    evaluations = [
        _route_evaluation(
            route,
            org_id=org_id,
            site_id=site_id,
            event_type=normalized_event_type,
            severity=normalized_severity,
        )
        for route in routes
    ]
    matched = [evaluation for evaluation in evaluations if evaluation["matched"]]
    if matched:
        best_specificity = max(int(evaluation.get("specificity") or 0) for evaluation in matched)
        best_priority = max(
            int(evaluation.get("priority") or 0)
            for evaluation in matched
            if int(evaluation.get("specificity") or 0) == best_specificity
        )
    else:
        best_specificity = None
        best_priority = None

    selected_routes: List[Dict[str, Any]] = []
    for evaluation in evaluations:
        if not evaluation["matched"]:
            continue
        specificity = int(evaluation.get("specificity") or 0)
        priority = int(evaluation.get("priority") or 0)
        if specificity == best_specificity and priority == best_priority:
            evaluation["selected"] = True
            selected_routes.append(evaluation)
            continue
        if best_specificity is not None and specificity < best_specificity:
            evaluation["reasons"].append("lower_specificity_than_selected")
        elif best_priority is not None and priority < best_priority:
            evaluation["reasons"].append("lower_priority_than_selected")

    return {
        "request": {
            "org_id": _as_text(org_id) or "",
            "site_id": _as_text(site_id) or "",
            "event_type": normalized_event_type,
            "severity": normalized_severity,
        },
        "selected_routes": selected_routes,
        "evaluated_routes": evaluations,
    }


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


def _matches_contains_filter(record_value: Any, filter_value: Optional[str]) -> bool:
    normalized_filter = (_as_text(filter_value) or "").strip().lower()
    if not normalized_filter or normalized_filter == "all":
        return True
    normalized_record = (_as_text(record_value) or "").strip().lower()
    return normalized_filter in normalized_record


def _normalize_status(value: Any) -> str:
    normalized = (_as_text(value) or "").strip().lower()
    return normalized if normalized in {"sent", "failed", "skipped"} else ""


def _normalize_filter_status(value: Optional[str]) -> Optional[str]:
    text = (_as_text(value) or "").strip().lower()
    if not text or text == "all":
        return None
    return _normalize_status(text) or None


def _normalize_filter_severity(value: Optional[str]) -> Optional[str]:
    text = (_as_text(value) or "").strip().lower()
    if not text or text == "all":
        return None
    normalized = _normalize_severity(text, default="")
    return normalized or None


def _normalize_filter_text(value: Optional[str]) -> Optional[str]:
    text = (_as_text(value) or "").strip()
    if not text or text.lower() == "all":
        return None
    return text


def _edge_correlation_fields(event_type: str, payload_data: Dict[str, Any]) -> Dict[str, Any]:
    if event_type != "edge.degraded":
        return {
            "edge_connectivity_status": "",
            "edge_buffered_event_count": None,
            "edge_queued_command_count": None,
            "edge_transition_count": None,
        }

    connectivity_status = (_as_text(payload_data.get("connectivity_status")) or "").strip().lower()
    if connectivity_status not in {"offline", "degraded", "unknown", "online"}:
        connectivity_status = ""

    def _as_int_or_none(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return {
        "edge_connectivity_status": connectivity_status,
        "edge_buffered_event_count": _as_int_or_none(payload_data.get("buffered_event_count")),
        "edge_queued_command_count": _as_int_or_none(payload_data.get("queued_command_count")),
        "edge_transition_count": _as_int_or_none(payload_data.get("transition_count")),
    }


def _sort_key_attempted_desc(record: Dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _as_text(record.get("attempted_at")) or "",
        _as_text(record.get("event_type")) or "",
        _as_text(record.get("route_id")) or "",
        _as_text(record.get("destination")) or "",
    )


def _sort_key_attempted_asc(record: Dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _as_text(record.get("attempted_at")) or "",
        _as_text(record.get("event_type")) or "",
        _as_text(record.get("route_id")) or "",
        _as_text(record.get("destination")) or "",
    )


def _sort_key_failures_first(record: Dict[str, Any]) -> tuple[int, str, str, str, str]:
    status = _normalize_status(record.get("status"))
    failure_rank = 0 if status == "failed" else 1
    return (
        failure_rank,
        _as_text(record.get("attempted_at")) or "",
        _as_text(record.get("event_type")) or "",
        _as_text(record.get("route_id")) or "",
        _as_text(record.get("destination")) or "",
    )


def _notification_policy(settings: Settings) -> Dict[str, Any]:
    raw = settings.notification_policy_json
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_scope_match(rule: Dict[str, Any], *, event_type: str, org_id: Optional[str], site_id: Optional[str]) -> bool:
    event_types = _as_text_list(rule.get("event_types") or rule.get("event_type"))
    if event_types and event_type not in event_types:
        return False
    org_ids = _as_text_list(rule.get("org_ids") or rule.get("org_id"))
    if org_ids and (_as_text(org_id) or "") not in org_ids:
        return False
    site_ids = _as_text_list(rule.get("site_ids") or rule.get("site_id"))
    if site_ids and (_as_text(site_id) or "") not in site_ids:
        return False
    return True


def _active_suppression(
    settings: Settings,
    *,
    event_type: str,
    org_id: Optional[str],
    site_id: Optional[str],
) -> Optional[str]:
    policy = _notification_policy(settings)
    suppressions = policy.get("suppressions")
    if not isinstance(suppressions, list):
        return None
    now = _utcnow()
    for suppression in suppressions:
        if not isinstance(suppression, dict):
            continue
        if not _is_scope_match(suppression, event_type=event_type, org_id=org_id, site_id=site_id):
            continue
        until_text = _as_text(suppression.get("until"))
        if until_text:
            candidate = until_text.replace("Z", "+00:00")
            try:
                until = dt.datetime.fromisoformat(candidate)
            except ValueError:
                until = None
            if until is not None and until.tzinfo is None:
                until = until.replace(tzinfo=dt.timezone.utc)
            if until is not None and until < now:
                continue
        return _as_text(suppression.get("reason")) or "suppressed by notification policy"
    return None


def _escalation_applies(
    settings: Settings,
    records: List[Dict[str, Any]],
    *,
    event_type: str,
    org_id: Optional[str],
    site_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    policy = _notification_policy(settings)
    escalation = policy.get("escalation")
    if not isinstance(escalation, dict):
        return None
    threshold = escalation.get("failure_threshold")
    window_s = escalation.get("window_s")
    try:
        threshold_value = int(threshold)
        window_value = int(window_s)
    except (TypeError, ValueError):
        return None
    if threshold_value <= 0 or window_value <= 0:
        return None
    if not _is_scope_match(escalation, event_type=event_type, org_id=org_id, site_id=site_id):
        return None
    cutoff = _utcnow() - dt.timedelta(seconds=window_value)
    failures = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        if _normalize_status(record.get("status")) != "failed":
            continue
        if (_as_text(record.get("event_type")) or "") != event_type:
            continue
        if (_as_text(record.get("org_id")) or "") != (_as_text(org_id) or ""):
            continue
        if (_as_text(record.get("site_id")) or "") != (_as_text(site_id) or ""):
            continue
        attempted_at = _parsed_attempted_at(record)
        if attempted_at is None or attempted_at < cutoff:
            continue
        failures += 1
    if failures < threshold_value:
        return None
    return {
        "window_s": window_value,
        "failure_threshold": threshold_value,
        "observed_failures": failures,
    }


def _send_webhook(
    url: str, payload: Dict[str, Any], timeout_s: float
) -> tuple[bool, Optional[int], str]:
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(url, json=payload)
        if 200 <= response.status_code < 300:
            return True, response.status_code, ""
        return False, response.status_code, f"Webhook returned HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        return False, None, str(exc)


def _send_email(
    settings: Settings,
    recipients: List[str],
    payload: Dict[str, Any],
) -> tuple[bool, Optional[int], str]:
    if not recipients:
        return False, None, "No email recipient configured"
    if not settings.notification_smtp_host:
        return False, None, "SMTP host not configured"
    message = EmailMessage()
    subject_prefix = (_as_text(settings.notification_email_subject_prefix) or "").strip()
    event_type = _as_text(payload.get("event_type")) or "notification"
    severity = _as_text(payload.get("severity")) or "warning"
    message["Subject"] = f"{subject_prefix} {event_type} ({severity})".strip()
    message["From"] = settings.notification_email_from
    message["To"] = ", ".join(recipients)
    body_lines = [
        _as_text(payload.get("summary")) or "",
        "",
        f"Event: {event_type}",
        f"Severity: {severity}",
        f"Org: {_as_text(payload.get('org_id')) or '-'}",
        f"Site: {_as_text(payload.get('site_id')) or '-'}",
        f"Occurred at: {_as_text(payload.get('occurred_at')) or '-'}",
        "",
        "Payload:",
        json.dumps(payload.get("payload") or {}, sort_keys=True, indent=2),
    ]
    message.set_content("\n".join(body_lines))
    try:
        with smtplib.SMTP(
            host=settings.notification_smtp_host,
            port=settings.notification_smtp_port,
            timeout=settings.notification_smtp_timeout_s,
        ) as server:
            if settings.notification_smtp_use_tls:
                server.starttls()
            if settings.notification_smtp_username:
                server.login(
                    settings.notification_smtp_username,
                    settings.notification_smtp_password or "",
                )
            server.send_message(message)
        return True, 250, ""
    except Exception as exc:
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

    normalized_severity = _normalize_severity(severity)
    event_name = _as_text(event_type) or "unknown"
    policy_suppression = _active_suppression(
        settings,
        event_type=event_name,
        org_id=org_id,
        site_id=site_id,
    )
    payload_data = dict(payload) if isinstance(payload, dict) else {}
    if policy_suppression:
        attempted_at = _utcnow_text()
        record = {
            "attempted_at": attempted_at,
            "delivered_at": None,
            "channel": "policy",
            "status": "suppressed",
            "event_type": event_name,
            "severity": normalized_severity,
            "summary": _as_text(summary) or "",
            "org_id": _as_text(org_id) or "",
            "site_id": _as_text(site_id) or "",
            "route_id": "policy",
            "destination": "suppressed",
            "dedupe_key": _as_text(dedupe_key) or "",
            "response_status_code": None,
            "delivery_error": policy_suppression,
            "payload": payload_data,
        }
        _persist_record(settings, record)
        return {
            "event_type": event_name,
            "severity": normalized_severity,
            "org_id": _as_text(org_id) or "",
            "site_id": _as_text(site_id) or "",
            "status": "suppressed",
            "delivery_count": 1,
            "deliveries": [record],
        }

    escalation = _escalation_applies(
        settings,
        _load_records(settings),
        event_type=event_name,
        org_id=org_id,
        site_id=site_id,
    )
    if escalation is not None and normalized_severity != "critical":
        normalized_severity = "critical"
        payload_data = {
            **payload_data,
            "policy_escalation": {
                "applied": True,
                **escalation,
            },
        }

    selected_routes = _resolve_routes(
        settings,
        org_id=org_id,
        site_id=site_id,
        event_type=event_name,
        severity=normalized_severity,
    )
    attempted_at = _utcnow_text()
    edge_fields = _edge_correlation_fields(event_name, payload_data)

    if not selected_routes:
        record = {
            "attempted_at": attempted_at,
            "delivered_at": None,
            "channel": "webhook",
            "status": "skipped",
            "event_type": event_name,
            "severity": normalized_severity,
            "summary": _as_text(summary) or "",
            "org_id": _as_text(org_id) or "",
            "site_id": _as_text(site_id) or "",
            "route_id": "",
            "destination": "unconfigured",
            "dedupe_key": _as_text(dedupe_key) or "",
            "response_status_code": None,
            "delivery_error": "No webhook route configured",
            "payload": payload_data,
            **edge_fields,
        }
        _persist_record(settings, record)
        return record

    deliveries: List[Dict[str, Any]] = []
    for route in selected_routes:
        webhook_url = _as_text(route.get("webhook_url"))
        email_to = _normalize_email_list(route.get("email_to"))
        route_id = _as_text(route.get("route_id")) or ""
        channel_targets: List[tuple[str, Optional[str], List[str]]] = []
        if webhook_url:
            channel_targets.append(("webhook", webhook_url, []))
        if email_to:
            channel_targets.append(("email", None, email_to))
        if not channel_targets:
            channel_targets.append(("webhook", None, []))

        for channel, webhook_target, email_targets in channel_targets:
            destination = (
                _destination_label(webhook_target)
                if channel == "webhook"
                else ",".join(email_targets) or "unconfigured"
            )
            record = {
                "attempted_at": attempted_at,
                "delivered_at": None,
                "channel": channel,
                "status": "skipped",
                "event_type": event_name,
                "severity": normalized_severity,
                "summary": _as_text(summary) or "",
                "org_id": _as_text(org_id) or "",
                "site_id": _as_text(site_id) or "",
                "route_id": route_id,
                "destination": destination,
                "dedupe_key": _as_text(dedupe_key) or "",
                "response_status_code": None,
                "delivery_error": "",
                "payload": payload_data,
                **edge_fields,
            }

            if channel == "webhook":
                if not webhook_target:
                    record["delivery_error"] = "No webhook route configured"
                    _persist_record(settings, record)
                    deliveries.append(record)
                    continue
                delivered, status_code, error = _send_webhook(
                    webhook_target,
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
            else:
                delivered, status_code, error = _send_email(
                    settings,
                    email_targets,
                    {
                        "event_type": record["event_type"],
                        "severity": record["severity"],
                        "summary": record["summary"],
                        "org_id": record["org_id"],
                        "site_id": record["site_id"],
                        "occurred_at": attempted_at,
                        "payload": record["payload"],
                    },
                )
            record["response_status_code"] = status_code
            if delivered:
                record["status"] = "sent"
                record["delivered_at"] = attempted_at
            else:
                record["status"] = "failed"
                record["delivery_error"] = error
            _persist_record(settings, record)
            deliveries.append(record)

    overall_status = "sent"
    if any((_as_text(record.get("status")) or "") == "failed" for record in deliveries):
        overall_status = "failed"
    elif all((_as_text(record.get("status")) or "") == "skipped" for record in deliveries):
        overall_status = "skipped"

    return {
        "event_type": event_name,
        "severity": normalized_severity,
        "org_id": _as_text(org_id) or "",
        "site_id": _as_text(site_id) or "",
        "status": overall_status,
        "delivery_count": len(deliveries),
        "deliveries": deliveries,
    }


def recent_notification_deliveries(
    *,
    limit: int = 6,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    event_type: Optional[str] = None,
    destination: Optional[str] = None,
    route_id: Optional[str] = None,
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    edge_state: Optional[str] = None,
    sort: str = "failures_first",
    settings: Optional[Settings] = None,
) -> List[Dict[str, Any]]:
    settings = settings or Settings()
    records = _load_records(settings)
    status_filter = _normalize_filter_status(status)
    severity_filter = _normalize_filter_severity(severity)
    event_type_filter = _normalize_filter_text(event_type)
    destination_filter = _normalize_filter_text(destination)
    route_filter = _normalize_filter_text(route_id)
    org_filter = _normalize_filter_text(org_id)
    site_filter = _normalize_filter_text(site_id)
    edge_state_filter = (_normalize_filter_text(edge_state) or "").lower() or None
    if edge_state_filter and edge_state_filter not in {"offline", "degraded", "unknown", "online"}:
        edge_state_filter = None

    filtered = [
        record
        for record in records
        if isinstance(record, dict)
        and (status_filter is None or _normalize_status(record.get("status")) == status_filter)
        and (severity_filter is None or _normalize_severity(record.get("severity"), default="") == severity_filter)
        and (event_type_filter is None or (_as_text(record.get("event_type")) or "") == event_type_filter)
        and (route_filter is None or (_as_text(record.get("route_id")) or "") == route_filter)
        and (org_filter is None or (_as_text(record.get("org_id")) or "") == org_filter)
        and (site_filter is None or (_as_text(record.get("site_id")) or "") == site_filter)
        and (edge_state_filter is None or (_as_text(record.get("edge_connectivity_status")) or "").lower() == edge_state_filter)
        and _matches_contains_filter(record.get("destination"), destination_filter)
    ]

    normalized_sort = (_as_text(sort) or "failures_first").strip().lower()
    if normalized_sort == "recent":
        ordered = sorted(filtered, key=_sort_key_attempted_desc, reverse=True)
    elif normalized_sort == "oldest":
        ordered = sorted(filtered, key=_sort_key_attempted_asc)
    else:
        ordered = sorted(filtered, key=_sort_key_attempted_desc, reverse=True)
        failed = [record for record in ordered if _normalize_status(record.get("status")) == "failed"]
        non_failed = [record for record in ordered if _normalize_status(record.get("status")) != "failed"]
        ordered = failed + non_failed
    return ordered[: max(1, int(limit))]
