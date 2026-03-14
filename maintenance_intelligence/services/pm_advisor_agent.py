from typing import Any, Dict, List, Optional


def _draft_actions(recommendation: Dict[str, Any]) -> List[str]:
    actions = recommendation.get("immediate_actions") or []
    if actions:
        return [str(action) for action in actions[:3]]
    title = (recommendation.get("title") or "maintenance issue").strip()
    return [
        f"Inspect the affected asset before the next planned outage: {title}",
        "Confirm spare parts, labor window, and lockout requirements.",
    ]


def analyze_pm_strategy(
    recommendation: Dict[str, Any], context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    context = context or {}
    actions = _draft_actions(recommendation)
    asset_id = recommendation.get("asset_id") or "unknown-asset"
    evidence = recommendation.get("evidence") or []
    return {
        "proposal_title": f"PM plan for {asset_id}",
        "proposal_summary": (
            "Review RCA evidence, convert the recommendation into a planned maintenance change, "
            "and confirm the execution window with site operations."
        ),
        "recommended_actions": actions,
        "playbook_query": recommendation.get("title") or recommendation.get("rationale") or asset_id,
        "metadata": {
            "source": "pm_advisor_stub",
            "evidence_count": len(evidence),
            "context_keys": sorted(context.keys()),
        },
    }