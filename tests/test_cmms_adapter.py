import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services.cmms import MockCMMSConnector, get_cmms_adapter


def test_mock_cmms_connector_generates_draft_payload():
    connector = MockCMMSConnector()

    result = connector.submit_proposal(
        {
            "proposal_id": "PMP-1234567890ab",
            "org_id": "org-demo",
            "proposer_subject": "planner@example.com",
            "asset_id": "PUMP-101",
            "proposal_title": "Bearing replacement plan",
            "proposal_summary": "Schedule inspection and bearing swap.",
            "recommended_actions": ["Inspect bearings", "Stage parts", "Swap bearing"],
            "playbook_refs": [{"playbook_id": "PB-101"}],
            "metadata": {"priority": "high", "source": "test"},
        },
        approved_by="approver@example.com",
        notes="Create draft before shutdown window.",
    )

    assert result["status"] == "queued"
    assert result["connector"] == "mock"
    assert result["cms_reference"] == "WO-1234567890ab"
    assert result["work_order"]["status"] == "DRAFT"
    assert result["work_order"]["priority"] == "HIGH"
    assert result["work_order"]["metadata"]["proposal_id"] == "PMP-1234567890ab"
    assert "Planner notes: Create draft before shutdown window." in result["work_order"]["description"]


def test_get_cmms_adapter_rejects_unknown_backend():
    settings = Settings(MI_PM_CONNECTOR_BACKEND="unsupported")

    with pytest.raises(ValueError, match="Unsupported PM connector backend"):
        get_cmms_adapter(settings)