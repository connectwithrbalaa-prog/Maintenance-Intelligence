import importlib
import datetime as dt
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_intelligence.api.main import app
from maintenance_intelligence.services import wo_bridge as wo_bridge_mod

pm_mod = importlib.import_module("maintenance_intelligence.api.pm_advisor")


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.rows = []
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        if "INSERT INTO pm_change_proposals" in query:
            self.state["proposal"] = {
                "proposal_id": params[0],
                "org_id": params[1],
                "proposer_subject": params[2],
                "run_id": params[3],
                "recommendation_id": params[4],
                "asset_id": params[5],
                "proposal_title": params[6],
                "proposal_summary": params[7],
                "recommended_actions": ["Inspect bearings", "Stage parts"],
                "playbook_refs": [{"playbook_id": "PB-CONNECTOR-001"}],
                "status": params[10],
                "approved_by": None,
                "approved_at": None,
                "cms_reference": None,
                "metadata": {"source": "connector-test", "priority": "medium"},
                "created_at": dt.datetime(2026, 3, 14, 18, 0, 0),
                "updated_at": dt.datetime(2026, 3, 14, 18, 0, 0),
            }
            return
        if "FROM pm_change_proposals\n                WHERE proposal_id" in query:
            proposal = self.state.get("proposal")
            self.row = None
            if proposal and proposal["proposal_id"] == params[0] and proposal["org_id"] == params[1]:
                self.row = (
                    proposal["proposal_id"],
                    proposal["org_id"],
                    proposal["proposer_subject"],
                    proposal["run_id"],
                    proposal["recommendation_id"],
                    proposal["asset_id"],
                    proposal["proposal_title"],
                    proposal["proposal_summary"],
                    proposal["recommended_actions"],
                    proposal["playbook_refs"],
                    proposal["metadata"],
                )
            return
        if "UPDATE pm_change_proposals" in query:
            proposal = self.state["proposal"]
            proposal["status"] = params[0]
            proposal["approved_by"] = params[1]
            proposal["approved_at"] = dt.datetime(2026, 3, 14, 18, 5, 0)
            proposal["cms_reference"] = params[2]
            proposal["updated_at"] = dt.datetime(2026, 3, 14, 18, 5, 0)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return FakeCursor(self.state)

    def close(self):
        return None


class RecordingConnector:
    def __init__(self):
        self.calls = []

    def submit_proposal(self, proposal, *, approved_by=None, notes=None):
        self.calls.append(
            {"proposal": proposal, "approved_by": approved_by, "notes": notes}
        )
        return {
            "status": "queued",
            "connector": "recording",
            "cms_reference": "WO-ADAPTER-001",
            "approved_by": approved_by,
            "notes": notes,
            "proposal_id": proposal.get("proposal_id"),
        }


def test_pm_advisor_approval_uses_cmms_connector(monkeypatch):
    state = {}
    connector = RecordingConnector()
    monkeypatch.setattr(pm_mod, "with_pg", lambda dsn: FakeConnection(state))
    monkeypatch.setattr(
        pm_mod,
        "analyze_pm_strategy",
        lambda recommendation, context=None, identity=None: {
            "proposal_title": "PM plan for PUMP-101",
            "proposal_summary": "Create a draft work order through connector boundary.",
            "recommended_actions": ["Inspect bearings", "Stage parts"],
            "playbook_query": "bearing plan",
            "metadata": {"source": "connector-test", "identity": identity or {}},
        },
    )
    monkeypatch.setattr(pm_mod, "search_playbooks", lambda query, asset_id=None, limit=5: [])
    monkeypatch.setattr(wo_bridge_mod, "get_cmms_adapter", lambda settings=None: connector)

    client = TestClient(app)
    created = client.post(
        "/api/v1/agents/pm/advisor/analyze",
        json={
            "run_id": "RUN-CONNECTOR-1",
            "recommendation_id": "REC-CONNECTOR-1",
            "asset_id": "PUMP-101",
            "title": "Bearing wear",
            "metadata": {"priority": "medium"},
        },
    )
    assert created.status_code == 200

    proposal_id = created.json()["proposal_id"]
    approved = client.post(
        f"/api/v1/agents/pm/proposals/{proposal_id}/approve",
        json={"approved_by": "planner@example.com", "notes": "Queue for next outage"},
    )

    assert approved.status_code == 200
    body = approved.json()
    assert body["cms_result"]["connector"] == "recording"
    assert body["cms_result"]["cms_reference"] == "WO-ADAPTER-001"
    assert connector.calls[0]["approved_by"] == "planner@example.com"
    assert connector.calls[0]["notes"] == "Queue for next outage"
    assert connector.calls[0]["proposal"]["proposal_id"] == proposal_id