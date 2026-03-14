from typing import Any, Dict, List, Optional


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
    return results[:limit]