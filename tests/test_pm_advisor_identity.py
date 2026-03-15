import importlib
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_intelligence.api.main import app
from maintenance_intelligence.multitenancy import TenantContext

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
                "recommended_actions": ["Inspect bearings"],
                "playbook_refs": [{"playbook_id": "PB-ID-001"}],
                "status": params[10],
                "approved_by": None,
                "approved_at": None,
                "cms_reference": None,
                "metadata": {"source": "identity-test"},
                "created_at": None,
                "updated_at": None,
            }
            return
        if "FROM pm_change_proposals\n                WHERE org_id" in query:
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
            proposal = self.state.get("proposal")
            if proposal:
                proposal["status"] = params[0]
                proposal["approved_by"] = params[1]
                proposal["cms_reference"] = params[2]

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


def test_pm_advisor_identity_header_fallback(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "1")
    state = {}
    monkeypatch.setattr(pm_mod, "with_pg", lambda dsn: FakeConnection(state))
    monkeypatch.setattr(
        pm_mod,
        "analyze_pm_strategy",
        lambda recommendation, context=None, identity=None: {
            "proposal_title": "PM plan for PUMP-101",
            "proposal_summary": "Header identity path.",
            "recommended_actions": ["Inspect bearings"],
            "playbook_query": "bearing review",
            "metadata": {"identity": identity or {}},
        },
    )
    monkeypatch.setattr(pm_mod, "search_playbooks", lambda query, asset_id=None, limit=5: [])
    monkeypatch.setattr(
        pm_mod,
        "push_work_order_to_cms",
        lambda proposal, approved_by=None, notes=None: {
            "cms_reference": "WO-ID-001",
            "handoff_complete": True,
        },
    )

    client = TestClient(app)
    headers = {"X-Org-Id": "org-header", "X-Role": "operator", "X-Subject": "header-user"}

    created = client.post(
        "/api/v1/agents/pm/advisor/analyze",
        headers=headers,
        json={
            "run_id": "RUN-ID-1",
            "recommendation_id": "REC-ID-1",
            "asset_id": "PUMP-101",
            "title": "Bearing wear",
            "metadata": {},
        },
    )

    assert created.status_code == 200
    body = created.json()
    assert body["org_id"] == "org-header"
    assert body["proposer_subject"] == "header-user"

    approved = client.post(
        f"/api/v1/agents/pm/proposals/{body['proposal_id']}/approve",
        headers=headers,
        json={"notes": "approve with header identity"},
    )
    assert approved.status_code == 200
    assert approved.json()["org_id"] == "org-header"
    assert approved.json()["proposer_subject"] == "header-user"


def test_pm_advisor_identity_header_fallback_disabled(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/v1/agents/pm/advisor/analyze",
        headers={"X-Org-Id": "org-header", "X-Role": "operator", "X-Subject": "header-user"},
        json={
            "run_id": "RUN-ID-DISABLED",
            "recommendation_id": "REC-ID-DISABLED",
            "asset_id": "PUMP-909",
            "title": "Disabled fallback",
            "metadata": {},
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authenticated identity required"


def test_pm_advisor_identity_request_state_user(monkeypatch):
    state = {}
    monkeypatch.setattr(pm_mod, "with_pg", lambda dsn: FakeConnection(state))
    monkeypatch.setattr(
        pm_mod,
        "analyze_pm_strategy",
        lambda recommendation, context=None, identity=None: {
            "proposal_title": "PM plan for PUMP-202",
            "proposal_summary": "Middleware identity path.",
            "recommended_actions": ["Inspect motor coupling"],
            "playbook_query": "coupling review",
            "metadata": {"identity": identity or {}},
        },
    )
    monkeypatch.setattr(pm_mod, "search_playbooks", lambda query, asset_id=None, limit=5: [])

    class InjectUserMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = TenantContext(
                org_id="org-middleware", role="operator", subject="middleware-user"
            )
            return await call_next(request)

    temp_app = FastAPI()
    temp_app.add_middleware(InjectUserMiddleware)
    temp_app.include_router(pm_mod.router)

    client = TestClient(temp_app)
    created = client.post(
        "/api/v1/agents/pm/advisor/analyze",
        json={
            "run_id": "RUN-ID-2",
            "recommendation_id": "REC-ID-2",
            "asset_id": "PUMP-202",
            "title": "Coupling drift",
            "metadata": {},
        },
    )
    assert created.status_code == 200
    assert created.json()["org_id"] == "org-middleware"
    assert created.json()["proposer_subject"] == "middleware-user"