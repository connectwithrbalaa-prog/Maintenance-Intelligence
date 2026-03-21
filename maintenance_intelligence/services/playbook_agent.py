from typing import Any, Dict, List, Optional

from loguru import logger


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _as_score(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def normalize_playbook_results(results: Any, asset_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if not isinstance(results, list):
        logger.warning("playbook.search.payload_malformed asset_id={} raw_payload={}", asset_id, results)
        return []

    normalized: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            logger.warning("playbook.search.item_malformed asset_id={} raw_payload={}", asset_id, item)
            continue
        playbook_id = _as_text(item.get("playbook_id"))
        title = _as_text(item.get("title"))
        summary = _as_text(item.get("summary"))
        if not any([playbook_id, title, summary]):
            logger.warning("playbook.search.item_empty asset_id={} raw_payload={}", asset_id, item)
            continue
        entry = {
            "playbook_id": playbook_id,
            "title": title,
            "summary": summary,
            "asset_id": _as_text(item.get("asset_id")) or asset_id,
            "score": _as_score(item.get("score")),
        }
        normalized.append({key: value for key, value in entry.items() if value is not None})
    return normalized


def search_playbooks(query: str, asset_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    trimmed_query = (query or "planned maintenance").strip() or "planned maintenance"
    results = [
        {
            "playbook_id": "PB-STUB-001",
            "title": "Inspect and stage maintenance window",
            "summary": "Validate tooling, parts, and lockout steps before scheduling the job.",
            "asset_id": asset_id,
            "score": 0.91,
        },
        {
            "playbook_id": "PB-STUB-002",
            "title": "Convert RCA recommendation into planner task",
            "summary": "Package evidence, risk notes, and approval details for the planner queue.",
            "asset_id": asset_id,
            "score": 0.84,
        },
        {
            "playbook_id": "PB-STUB-003",
            "title": f"Follow-up for {trimmed_query[:40]}",
            "summary": "Template for site-specific PM review and CMS handoff.",
            "asset_id": asset_id,
            "score": 0.76,
        },
    ]
    return normalize_playbook_results(results[:limit], asset_id=asset_id)