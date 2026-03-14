import importlib
import datetime as dt
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_intelligence.api.main import app

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
            proposal = {
                "proposal_id": params[0],
                "org_id": params[1],
                "run_id": params[2],
                "recommendation_id": params[3],
                "asset_id": params[4],
                "proposal_title": params[5],
                "proposal_summary": params[6],
                "recommended_actions": ["Inspect bearings"],
                "playbook_refs": [{"playbook_id": "PB-STUB-001"}],
                "status": params[9],
                "approved_by": None,
                "approved_at": None,
                "cms_reference": None,
                "metadata": {"source": "test"},
                "created_at": dt.datetime(2026, 3, 14, 18, 0, 0),
                "updated_at": dt.datetime(2026, 3, 14, 18, 0, 0),
            }
            self.state["proposal"] = proposal
        elif "FROM pm_change_proposals\n                WHERE proposal_id" in query:
            proposal = self.state.get("proposal")
            self.row = None
            if proposal and proposal["proposal_id"] == params[0] and proposal["org_id"] == params[1]:
                self.row = (
                    proposal["proposal_id"],
                    proposal["run_id"],
                    proposal["recommendation_id"],
                    proposal["asset_id"],
                    proposal["proposal_title"],
                    proposal["proposal_summary"],
                    proposal["recommended_actions"],
                    proposal["playbook_refs"],
                    proposal["metadata"],
                )
        elif "FROM pm_change_proposals\n                WHERE org_id" in query:
            proposal = self.state.get("proposal")
            self.rows = []
            if proposal and proposal["org_id"] == params[0]:
                self.rows = [
                    (
                        proposal["proposal_id"],
                        proposal["run_id"],
                        proposal["recommendation_id"],
                        proposal["asset_id"],
                        proposal["proposal_title"],
                        proposal["proposal_summary"],
                        proposal["recommended_actions"],
                        proposal["playbook_refs"],
                        proposal["status"],
                        proposal["approved_by"],
                        proposal["approved_at"],
                        proposal["cms_reference"],
                        proposal["metadata"],
                        proposal["created_at"],
                        proposal["updated_at"],
                    )
                ]
        elif "UPDATE pm_change_proposals" in query:
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


def test_pm_advisor_routes(monkeypatch):
    state = {}
    monkeypatch.setattr(pm_mod, "with_pg", lambda dsn: FakeConnection(state))
    monkeypatch.setattr(
        pm_mod,
        "analyze_pm_strategy",
        lambda recommendation, context=None: {
            "proposal_title": "PM plan for PUMP-101",
            "proposal_summary": "Schedule inspection and bearing swap.",
            "recommended_actions": ["Inspect bearings"],
            "playbook_query": "bearing swap",
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(
        pm_mod,
        "search_playbooks",
        lambda query, asset_id=None, limit=5: [{"playbook_id": "PB-STUB-001", "title": query}],
    )
    monkeypatch.setattr(
        pm_mod,
        "push_work_order_to_cms",
        lambda proposal, approved_by=None, notes=None: {
            "status": "queued",
            "cms_reference": "CMS-123",
            "approved_by": approved_by,
            "notes": notes,
        },
    )

    client = TestClient(app)

    analyze = client.post(
        "/api/v1/agents/pm/advisor/analyze",
        json={
            "run_id": "RUN-1",
            "recommendation_id": "REC-1",
            "asset_id": "PUMP-101",
            "title": "Bearing wear",
            "rationale": "RCA suggests progressive bearing wear.",
            "evidence": ["E1"],
            "immediate_actions": ["Inspect bearings"],
            "metadata": {"source_run": "summary"},
        },
    )
    assert analyze.status_code == 200
    proposal_id = analyze.json()["proposal_id"]

    playbooks = client.post(
        "/api/v1/agents/playbooks/search",
        json={"query": "bearing swap", "asset_id": "PUMP-101", "limit": 3},
    )
    assert playbooks.status_code == 200
    assert playbooks.json()["results"][0]["playbook_id"] == "PB-STUB-001"

    listed = client.get("/api/v1/agents/pm/proposals")
    assert listed.status_code == 200
    assert listed.json()[0]["proposal_id"] == proposal_id

    approved = client.post(
        f"/api/v1/agents/pm/proposals/{proposal_id}/approve",
        json={"approved_by": "planner@example.com", "notes": "Create work order draft"},
    )
    assert approved.status_code == 200
    assert approved.json()["cms_result"]["cms_reference"] == "CMS-123"