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
                "proposer_subject": params[2],
                "run_id": params[3],
                "recommendation_id": params[4],
                "asset_id": params[5],
                "proposal_title": params[6],
                "proposal_summary": params[7],
                "recommended_actions": ["Inspect bearings"],
                "playbook_refs": [{"playbook_id": "PB-STUB-001"}],
                "status": params[10],
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
        elif "FROM pm_change_proposals\n                WHERE org_id" in query:
            proposal = self.state.get("proposal")
            self.rows = []
            if proposal and proposal["org_id"] == params[0]:
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
        lambda recommendation, context=None, identity=None: {
            "proposal_title": "PM plan for PUMP-101",
            "proposal_summary": "Schedule inspection and bearing swap.",
            "recommended_actions": ["Inspect bearings"],
            "playbook_query": "bearing swap",
            "metadata": {"source": "test", "identity": identity or {}},
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
    assert analyze.json()["org_id"] == "default-org"
    assert analyze.json()["proposer_subject"] == "anonymous"

    playbooks = client.post(
        "/api/v1/agents/playbooks/search",
        json={"query": "bearing swap", "asset_id": "PUMP-101", "limit": 3},
    )
    assert playbooks.status_code == 200
    assert playbooks.json()["results"][0]["playbook_id"] == "PB-STUB-001"

    listed = client.get("/api/v1/agents/pm/proposals")
    assert listed.status_code == 200
    assert listed.json()[0]["proposal_id"] == proposal_id
    assert listed.json()[0]["proposer_subject"] == "anonymous"

    approved = client.post(
        f"/api/v1/agents/pm/proposals/{proposal_id}/approve",
        json={"approved_by": "planner@example.com", "notes": "Create work order draft"},
    )
    assert approved.status_code == 200
    assert approved.json()["cms_result"]["cms_reference"] == "CMS-123"
    assert approved.json()["proposer_subject"] == "anonymous"


def test_list_pm_proposals_coerces_malformed_nested_fields(monkeypatch):
    state = {
        "proposal": {
            "proposal_id": 987,
            "org_id": "default-org",
            "proposer_subject": "anonymous",
            "run_id": ["RUN-1"],
            "recommendation_id": True,
            "asset_id": "PUMP-101",
            "proposal_title": ["bad-title"],
            "proposal_summary": {"bad": "summary"},
            "recommended_actions": "not-a-list",
            "playbook_refs": ["bad-playbook", {"playbook_id": "PB-STUB-001"}],
            "status": ["draft"],
            "approved_by": {"user": "planner"},
            "approved_at": None,
            "cms_reference": 44,
            "metadata": "not-a-dict",
            "created_at": dt.datetime(2026, 3, 14, 18, 0, 0),
            "updated_at": dt.datetime(2026, 3, 14, 18, 0, 0),
        }
    }
    monkeypatch.setattr(pm_mod, "with_pg", lambda dsn: FakeConnection(state))

    client = TestClient(app)

    listed = client.get("/api/v1/agents/pm/proposals")

    assert listed.status_code == 200
    payload = listed.json()
    assert payload[0]["proposal_id"] == "987"
    assert payload[0]["run_id"] is None
    assert payload[0]["recommendation_id"] is None
    assert payload[0]["proposal_title"] is None
    assert payload[0]["proposal_summary"] is None
    assert payload[0]["recommended_actions"] == []
    assert payload[0]["playbook_refs"] == [{"playbook_id": "PB-STUB-001"}]
    assert payload[0]["status"] == "unknown"
    assert payload[0]["approved_by"] is None
    assert payload[0]["cms_reference"] == "44"
    assert payload[0]["metadata"] == {}


def test_approve_pm_proposal_coerces_malformed_nested_fields(monkeypatch):
    state = {
        "proposal": {
            "proposal_id": "PMP-1",
            "org_id": "default-org",
            "proposer_subject": "anonymous",
            "run_id": ["RUN-1"],
            "recommendation_id": 77,
            "asset_id": "PUMP-101",
            "proposal_title": ["bad-title"],
            "proposal_summary": {"bad": "summary"},
            "recommended_actions": "not-a-list",
            "playbook_refs": ["bad-playbook"],
            "status": "draft",
            "approved_by": None,
            "approved_at": None,
            "cms_reference": None,
            "metadata": "not-a-dict",
            "created_at": dt.datetime(2026, 3, 14, 18, 0, 0),
            "updated_at": dt.datetime(2026, 3, 14, 18, 0, 0),
        }
    }
    captured = {}
    monkeypatch.setattr(pm_mod, "with_pg", lambda dsn: FakeConnection(state))
    monkeypatch.setattr(
        pm_mod,
        "push_work_order_to_cms",
        lambda proposal, approved_by=None, notes=None: captured.setdefault("proposal", proposal)
        or {"status": "queued", "cms_reference": "CMS-123", "approved_by": approved_by, "notes": notes},
    )

    client = TestClient(app)

    approved = client.post(
        "/api/v1/agents/pm/proposals/PMP-1/approve",
        json={"approved_by": "planner@example.com", "notes": "Create work order draft"},
    )

    assert approved.status_code == 200
    assert captured["proposal"]["run_id"] is None
    assert captured["proposal"]["recommendation_id"] == "77"
    assert captured["proposal"]["proposal_title"] is None
    assert captured["proposal"]["proposal_summary"] is None
    assert captured["proposal"]["recommended_actions"] == []
    assert captured["proposal"]["playbook_refs"] == []
    assert captured["proposal"]["metadata"] == {}