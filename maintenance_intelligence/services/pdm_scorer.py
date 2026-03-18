from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple


_EVENT_SEVERITY_POINTS = {
    "critical": 28.0,
    "high": 20.0,
    "medium": 12.0,
    "low": 6.0,
}

_ROLLUP_PERIOD_POINTS = {
    "1h": 8.0,
    "6h": 5.0,
    "24h": 3.0,
}

_STATUS_ORDER = {
    "critical": 3,
    "elevated": 2,
    "watch": 1,
    "normal": 0,
}


def empty_early_warning_summary() -> Dict[str, Any]:
    return {
        "total_assets": 0,
        "status_counts": {
            "critical": 0,
            "elevated": 0,
            "watch": 0,
            "normal": 0,
        },
        "top_assets": [],
        "last_evaluated_at": None,
    }


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return float(candidate)
        except ValueError:
            return None
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = _coerce_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _to_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _asset_state(asset_id: str) -> Dict[str, Any]:
    return {
        "asset_id": asset_id,
        "event_count": 0,
        "last_event_at": None,
        "max_severity_points": 0.0,
        "high_severity_count": 0,
        "vibration_peak": None,
        "temperature_peak": None,
        "threshold_breach_count": 0,
        "anomaly_flag_points": 0.0,
        "anomaly_flag_count": 0,
        "rollup_vibration_peak": None,
        "rollup_temperature_peak": None,
        "last_signal_at": None,
    }


def _max_value(current: float | None, candidate: float | None) -> float | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return max(current, candidate)


def _update_event_state(asset: Dict[str, Any], severity: Any, occurred_at: Any, details: Any) -> None:
    asset["event_count"] = int(asset.get("event_count") or 0) + 1
    event_at = _parse_timestamp(occurred_at)
    if event_at and (asset.get("last_event_at") is None or event_at > asset["last_event_at"]):
        asset["last_event_at"] = event_at

    severity_key = (_coerce_text(severity) or "").lower()
    severity_points = float(_EVENT_SEVERITY_POINTS.get(severity_key, 0.0))
    asset["max_severity_points"] = max(float(asset.get("max_severity_points") or 0.0), severity_points)
    if severity_key in {"critical", "high"}:
        asset["high_severity_count"] = int(asset.get("high_severity_count") or 0) + 1

    payload = details if isinstance(details, dict) else {}
    vibration = _coerce_float(payload.get("rms"))
    temperature = _coerce_float(payload.get("temperature"))
    if temperature is None:
        temperature = _coerce_float(payload.get("temp"))
    threshold = _coerce_float(payload.get("threshold"))

    asset["vibration_peak"] = _max_value(asset.get("vibration_peak"), vibration)
    asset["temperature_peak"] = _max_value(asset.get("temperature_peak"), temperature)
    if threshold is not None:
        breached = False
        if vibration is not None and vibration > threshold:
            breached = True
        if temperature is not None and temperature > threshold:
            breached = True
        if breached:
            asset["threshold_breach_count"] = int(asset.get("threshold_breach_count") or 0) + 1


def _count_true_flags(flags: Any) -> int:
    if not isinstance(flags, dict):
        return 0
    return sum(1 for value in flags.values() if bool(value))


def _update_rollup_state(
    asset: Dict[str, Any],
    signal_type: Any,
    period: Any,
    end_time: Any,
    mean_value: Any,
    max_value: Any,
    anomaly_flags: Any,
) -> None:
    signal_key = (_coerce_text(signal_type) or "").lower()
    period_key = (_coerce_text(period) or "").lower()
    rollup_at = _parse_timestamp(end_time)
    if rollup_at and (asset.get("last_signal_at") is None or rollup_at > asset["last_signal_at"]):
        asset["last_signal_at"] = rollup_at

    flag_count = _count_true_flags(anomaly_flags)
    if flag_count > 0:
        asset["anomaly_flag_count"] = int(asset.get("anomaly_flag_count") or 0) + flag_count
        asset["anomaly_flag_points"] = float(asset.get("anomaly_flag_points") or 0.0) + (_ROLLUP_PERIOD_POINTS.get(period_key, 2.0) * flag_count)

    peak_value = _coerce_float(max_value)
    if peak_value is None:
        peak_value = _coerce_float(mean_value)
    if signal_key == "vibration":
        asset["rollup_vibration_peak"] = _max_value(asset.get("rollup_vibration_peak"), peak_value)
    elif signal_key == "temperature":
        asset["rollup_temperature_peak"] = _max_value(asset.get("rollup_temperature_peak"), peak_value)


def _reason_value(prefix: str, value: float | None, suffix: str) -> str | None:
    if value is None:
        return None
    return f"{prefix} {value:.1f}{suffix}"


def _score_asset(asset: Dict[str, Any], now: datetime) -> Tuple[float, str, List[str]]:
    reasons: List[str] = []
    score = float(asset.get("max_severity_points") or 0.0)

    event_count = int(asset.get("event_count") or 0)
    if event_count >= 1:
        score += min(18.0, float(event_count) * 6.0)

    if int(asset.get("high_severity_count") or 0) >= 2:
        reasons.append("High-severity events have repeated for this asset")

    anomaly_flag_points = min(24.0, float(asset.get("anomaly_flag_points") or 0.0))
    if anomaly_flag_points > 0:
        score += anomaly_flag_points
        reasons.append("Signal rollups still carry anomaly flags")

    threshold_breach_count = int(asset.get("threshold_breach_count") or 0)
    if threshold_breach_count > 0:
        score += min(10.0, float(threshold_breach_count) * 4.0)

    vibration_peak = _max_value(asset.get("vibration_peak"), asset.get("rollup_vibration_peak"))
    if vibration_peak is not None:
        if vibration_peak >= 10.0:
            score += 18.0
            reasons.append(_reason_value("Vibration remains at", vibration_peak, " mm/s") or "")
        elif vibration_peak >= 7.5:
            score += 10.0
            reasons.append(_reason_value("Vibration is trending high at", vibration_peak, " mm/s") or "")

    temperature_peak = _max_value(asset.get("temperature_peak"), asset.get("rollup_temperature_peak"))
    if temperature_peak is not None:
        if temperature_peak >= 90.0:
            score += 18.0
            reasons.append(_reason_value("Temperature remains at", temperature_peak, " C") or "")
        elif temperature_peak >= 80.0:
            score += 10.0
            reasons.append(_reason_value("Temperature is trending high at", temperature_peak, " C") or "")

    last_event_at = asset.get("last_event_at")
    if isinstance(last_event_at, datetime):
        age_hours = max(0.0, (now - last_event_at).total_seconds() / 3600.0)
        if age_hours <= 24:
            score += 12.0
            reasons.append("A fresh event landed within the last 24 hours")
        elif age_hours <= 72:
            score += 6.0

    if event_count >= 3:
        reasons.append("Event cadence is still elevated in the current window")

    score = round(min(100.0, score), 1)
    if score >= 70.0:
        status = "critical"
    elif score >= 45.0:
        status = "elevated"
    elif score >= 25.0:
        status = "watch"
    else:
        status = "normal"

    cleaned_reasons = [reason for reason in reasons if reason]
    deduped_reasons: List[str] = []
    for reason in cleaned_reasons:
        if reason not in deduped_reasons:
            deduped_reasons.append(reason)

    if not deduped_reasons and score > 0:
        deduped_reasons.append("Low-volume warning signals are present but not yet persistent")

    return score, status, deduped_reasons[:3]


def build_early_warning_report(
    event_rows: Iterable[Any],
    rollup_rows: Iterable[Any],
    *,
    now: datetime | None = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    anchor = now.astimezone(timezone.utc) if isinstance(now, datetime) else datetime.now(timezone.utc)
    per_asset: Dict[str, Dict[str, Any]] = {}

    for row in event_rows or []:
        if not row or not row[0]:
            continue
        asset_id = str(row[0])
        asset = per_asset.setdefault(asset_id, _asset_state(asset_id))
        _update_event_state(asset, row[1] if len(row) > 1 else None, row[2] if len(row) > 2 else None, row[3] if len(row) > 3 else None)

    for row in rollup_rows or []:
        if not row or not row[0]:
            continue
        asset_id = str(row[0])
        asset = per_asset.setdefault(asset_id, _asset_state(asset_id))
        _update_rollup_state(
            asset,
            row[1] if len(row) > 1 else None,
            row[2] if len(row) > 2 else None,
            row[3] if len(row) > 3 else None,
            row[4] if len(row) > 4 else None,
            row[5] if len(row) > 5 else None,
            row[6] if len(row) > 6 else None,
        )

    summary = empty_early_warning_summary()
    asset_metrics: Dict[str, Dict[str, Any]] = {}
    ranked_assets: List[Dict[str, Any]] = []

    for asset_id, asset in per_asset.items():
        score, status, reasons = _score_asset(asset, anchor)
        summary["total_assets"] = int(summary.get("total_assets") or 0) + 1
        status_counts = summary.setdefault("status_counts", {})
        status_counts[status] = int(status_counts.get(status) or 0) + 1

        asset_metrics[asset_id] = {
            "early_warning_score": score,
            "early_warning_status": status,
            "early_warning_reasons": reasons,
            "early_warning_last_event_at": _to_isoformat(asset.get("last_event_at")),
            "early_warning_last_signal_at": _to_isoformat(asset.get("last_signal_at")),
        }
        ranked_assets.append(
            {
                "asset_id": asset_id,
                "score": score,
                "status": status,
                "reasons": reasons,
            }
        )

    ranked_assets.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            -_STATUS_ORDER.get(str(item.get("status") or "normal"), 0),
            str(item.get("asset_id") or ""),
        )
    )
    summary["top_assets"] = ranked_assets[: max(1, int(top_n))] if ranked_assets else []
    summary["last_evaluated_at"] = _to_isoformat(anchor)
    return {
        "summary": summary,
        "asset_metrics": asset_metrics,
    }