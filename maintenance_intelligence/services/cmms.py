from typing import Any, Dict, Protocol

from maintenance_intelligence.runner.config import Settings


class CMMSConnector(Protocol):
    def submit_proposal(
        self,
        proposal: Dict[str, Any],
        *,
        approved_by: str | None = None,
        notes: str | None = None,
    ) -> Dict[str, Any]: ...


class MockCMMSConnector:
    connector_name = "mock"

    def submit_proposal(
        self,
        proposal: Dict[str, Any],
        *,
        approved_by: str | None = None,
        notes: str | None = None,
    ) -> Dict[str, Any]:
        proposal_id = str(proposal.get("proposal_id") or "unknown")
        work_order_id = f"WO-{proposal_id.replace('PMP-', '')[:12]}"
        description_parts = [proposal.get("proposal_summary") or "PM change proposal approved."]
        if notes:
            description_parts.append(f"Planner notes: {notes}")

        work_order = {
            "wo_id": work_order_id,
            "asset_id": proposal.get("asset_id"),
            "status": "DRAFT",
            "title": proposal.get("proposal_title") or f"PM draft for {proposal_id}",
            "description": "\n\n".join(description_parts),
            "priority": _infer_priority(proposal),
            "metadata": {
                "source": "pm-advisor-mock-connector",
                "proposal_id": proposal_id,
                "org_id": proposal.get("org_id"),
                "proposer_subject": proposal.get("proposer_subject"),
                "recommended_actions": proposal.get("recommended_actions") or [],
                "playbook_refs": proposal.get("playbook_refs") or [],
                "proposal_metadata": proposal.get("metadata") or {},
            },
        }
        return {
            "status": "queued",
            "connector": self.connector_name,
            "cms_reference": work_order_id,
            "approved_by": approved_by,
            "notes": notes,
            "proposal_id": proposal_id,
            "work_order": work_order,
            "message": "Mock connector generated a draft work order payload. Replace with a real connector when available.",
        }


def _infer_priority(proposal: Dict[str, Any]) -> str:
    metadata = proposal.get("metadata") or {}
    priority = metadata.get("priority") or metadata.get("recommended_priority")
    if isinstance(priority, str) and priority.strip():
        return priority.strip().upper()
    actions = proposal.get("recommended_actions") or []
    if len(actions) >= 3:
        return "HIGH"
    return "MEDIUM"


def get_cmms_adapter(settings: Settings | None = None) -> CMMSConnector:
    settings = settings or Settings()
    backend = (settings.pm_connector_backend or "mock").strip().lower()
    if backend == "mock":
        return MockCMMSConnector()
    raise ValueError(
        f"Unsupported PM connector backend '{settings.pm_connector_backend}'. Configure MI_PM_CONNECTOR_BACKEND=mock or add a real adapter."
    )