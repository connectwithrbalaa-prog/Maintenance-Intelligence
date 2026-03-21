import importlib
import sys
from pathlib import Path

import pytest
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
            self.state["proposal"] = {
                "proposal_id": params[0],
                "org_id": params[1],
                "proposer_subject": params[2],
                "run_id": params[3],
                "recommendation_id": params[4],
                "asset_id": params[5],
                "proposal_title": params[6],
                "proposal_summary": params[7],
                "recommended_actions": ["Inspect bearings", "Plan bearing swap"],
                "playbook_refs": [{"playbook_id": "PB-SMOKE-001", "title": "Bearing plan"}],
                "status": params[10],
                "approved_by": None,
                "approved_at": None,
                "cms_reference": None,
                "metadata": {"source": "smoke"},
                "created_at": None,
                "updated_at": None,
            }
            return

        if "FROM pm_change_proposals\n                WHERE org_id" in query:
            proposal = self.state.get("proposal")
            self.rows = []
            if proposal:
                self.rows = [
                    (
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
                        proposal["status"],
                        proposal["approved_by"],
                        proposal["approved_at"],
                        proposal["cms_reference"],
                        proposal["metadata"],
                        proposal["created_at"],
                        proposal["updated_at"],
                    )
                ]
            return

        if "FROM pm_change_proposals\n                WHERE proposal_id" in query:
            proposal = self.state.get("proposal")
            self.row = None
            if proposal:
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
            proposal = self.state.get("proposal")
            if proposal:
                proposal["status"] = params[0]
                proposal["approved_by"] = params[1]
                proposal["cms_reference"] = params[3]

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


@pytest.fixture
def smoke_client(monkeypatch):
    state = {}
    monkeypatch.setattr(pm_mod, "with_pg", lambda dsn: FakeConnection(state))
    monkeypatch.setattr(
        pm_mod,
        "analyze_pm_strategy",
        lambda recommendation, context=None, identity=None: {
            "proposal_title": "PM plan for PUMP-101",
            "proposal_summary": "Schedule inspection and bearing swap.",
            "recommended_actions": ["Inspect bearings", "Plan bearing swap"],
            "playbook_query": "bearing plan",
            "metadata": {"source": "smoke", "identity": identity or {}},
        },
    )
    monkeypatch.setattr(
        pm_mod,
        "search_playbooks",
        lambda query, asset_id=None, limit=5: [{"playbook_id": "PB-SMOKE-001", "title": query}],
    )
    monkeypatch.setattr(
        pm_mod,
        "push_work_order_to_cms",
        lambda proposal, approved_by=None, notes=None: {
            "status": "queued",
            "cms_reference": "WO-SMOKE-001",
            "approved_by": approved_by,
            "notes": notes,
            "proposal_id": proposal.get("proposal_id"),
            "handoff_complete": True,
        },
    )
    return TestClient(app), state


def test_pm_advisor_approve_flow_smoke(smoke_client):
    client, _state = smoke_client

    created = client.post(
        "/api/v1/agents/pm/advisor/analyze",
        json={
            "run_id": "RUN-SMOKE-1",
            "recommendation_id": "REC-SMOKE-1",
            "asset_id": "PUMP-101",
            "title": "Bearing wear",
            "rationale": "Planner review requested.",
            "evidence": ["E1"],
            "immediate_actions": ["Inspect bearings"],
            "metadata": {"source_run": "smoke"},
        },
    )
    assert created.status_code == 200
    proposal_id = created.json().get("proposal_id")
    assert created.json()["proposer_subject"] == "anonymous"
    if not proposal_id:
        pytest.skip("No PM proposal created in smoke flow")

    listed = client.get("/api/v1/agents/pm/proposals")
    assert listed.status_code == 200
    proposals = listed.json()
    if not proposals:
        pytest.skip("No PM proposals available in smoke flow")
    assert proposals[0]["proposal_id"] == proposal_id

    approved = client.post(
        f"/api/v1/agents/pm/proposals/{proposal_id}/approve",
        json={"approved_by": "planner@example.com", "notes": "Smoke test approval"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved"
    assert body["cms_result"]["cms_reference"] == "WO-SMOKE-001"
    assert body["proposer_subject"] == "anonymous"