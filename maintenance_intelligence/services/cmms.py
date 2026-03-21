from typing import Any, Dict, Optional, Protocol

from loguru import logger

from maintenance_intelligence.runner.config import Settings


class CMMSConnector(Protocol):
    def submit_proposal(
        self,
        proposal: Dict[str, Any],
        *,
        approved_by: str | None = None,
        notes: str | None = None,
    ) -> Dict[str, Any]: ...


class CMMSConnectorError(RuntimeError):
    pass


class CMMSConnectorUnavailableError(CMMSConnectorError):
    pass


class CMMSConnectorPayloadError(CMMSConnectorError):
    pass


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


def _normalize_work_order(value: Any, proposal_id: str) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        logger.warning(
            "cmms.connector.work_order_malformed proposal_id={} raw_payload={}",
            proposal_id,
            value,
        )
        return None
    return {
        "wo_id": _as_text(value.get("wo_id")),
        "asset_id": _as_text(value.get("asset_id")),
        "status": _as_text(value.get("status")) or "PENDING",
        "title": _as_text(value.get("title")),
        "description": _as_text(value.get("description")),
        "priority": _as_text(value.get("priority")),
        "metadata": _as_dict(value.get("metadata")),
    }


def normalize_connector_result(
    result: Any,
    *,
    proposal_id: str,
    connector_name: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(result, dict):
        logger.warning(
            "cmms.connector.payload_malformed proposal_id={} connector={} raw_payload={}",
            proposal_id,
            connector_name or "unknown",
            result,
        )
        raise CMMSConnectorPayloadError("Connector returned malformed payload")

    connector = _as_text(result.get("connector")) or connector_name or "unknown"
    normalized = {
        "status": (_as_text(result.get("status")) or "pending").lower(),
        "connector": connector,
        "cms_reference": _as_text(result.get("cms_reference")),
        "approved_by": _as_text(result.get("approved_by")),
        "notes": _as_text(result.get("notes")),
        "proposal_id": _as_text(result.get("proposal_id")) or proposal_id,
        "message": _as_text(result.get("message")),
        "work_order": _normalize_work_order(result.get("work_order"), proposal_id),
        "raw_response": result,
    }
    normalized["handoff_complete"] = bool(
        normalized["cms_reference"]
        or (normalized["work_order"] and normalized["work_order"].get("wo_id"))
    )
    if not normalized["handoff_complete"]:
        logger.warning(
            "cmms.connector.handoff_incomplete proposal_id={} connector={} raw_payload={}",
            proposal_id,
            connector,
            result,
        )
    return normalized


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
        return normalize_connector_result({
            "status": "queued",
            "connector": self.connector_name,
            "cms_reference": work_order_id,
            "approved_by": approved_by,
            "notes": notes,
            "proposal_id": proposal_id,
            "work_order": work_order,
            "message": "Mock connector generated a draft work order payload. Replace with a real connector when available.",
        }, proposal_id=proposal_id, connector_name=self.connector_name)


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
    raise CMMSConnectorUnavailableError(
        f"Unsupported PM connector backend '{settings.pm_connector_backend}'. Configure MI_PM_CONNECTOR_BACKEND=mock or add a real adapter."
    )