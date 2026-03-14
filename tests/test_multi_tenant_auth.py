import datetime as dt
import json

from fastapi.testclient import TestClient

from maintenance_intelligence.api import feedback as feedback_api
from maintenance_intelligence.api import main as main_api
from maintenance_intelligence.api import outcomes as outcomes_api
from maintenance_intelligence.api.main import app


class _Cursor:
    def __init__(self, calls):
        self.calls = calls
        self.rows = []

    def execute(self, query, params=None):
        params = tuple(params or ())
        self.calls.append((query, params))
        normalized = " ".join(query.split())
        if "FROM rca_feedback" in normalized and "GROUP BY action" in normalized:
            self.rows = [("accept", 2), ("reject", 1)]
        elif "FROM workorders w" in normalized and "COUNT(*) AS n" in normalized:
            self.rows = [("ASSET-1", 3)]
        elif normalized.startswith("SELECT wo_id, asset_id, metadata FROM workorders"):
            self.rows = [
                (
                    "WO-1",
                    "ASSET-1",
                    {"created_at": "2026-03-14T10:00:00Z", "resolved_at": "2026-03-14T11:00:00Z"},
                )
            ]
        elif normalized.startswith("SELECT event_id, asset_id, occurred_at FROM events"):
            self.rows = [
                ("EVT-1", "ASSET-1", dt.datetime(2026, 3, 14, 10, 30, tzinfo=dt.timezone.utc))
            ]
        elif "COUNT(*) FILTER (WHERE action = 'accept')" in normalized:
            self.rows = [("ASSET-1", 2, 3)]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self, calls):
        self.calls = calls

    def cursor(self, *args, **kwargs):
        return _Cursor(self.calls)

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_trigger_requires_operator_role(monkeypatch):
    monkeypatch.setenv("MI_AUTH_MODE", "api_key")
    monkeypatch.setenv(
        "MI_API_KEYS",
        json.dumps(
            {
                "viewer-key": {"org_id": "ORG-1", "role": "viewer"},
                "operator-key": {"org_id": "ORG-1", "role": "operator"},
            }
        ),
    )
    monkeypatch.setattr(
        main_api,
        "run",
        lambda event_id, settings, org_id=None: {"event_id": event_id, "org_id": org_id},
    )

    client = TestClient(app)
    denied = client.post(
        "/api/v1/agents/rca/trigger", json={"event_id": "E-1"}, headers={"X-API-Key": "viewer-key"}
    )
    allowed = client.post(
        "/api/v1/agents/rca/trigger",
        json={"event_id": "E-1"},
        headers={"X-API-Key": "operator-key"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["org_id"] == "ORG-1"


def test_feedback_uses_authenticated_org(monkeypatch):
    calls = []
    monkeypatch.setenv("MI_AUTH_MODE", "api_key")
    monkeypatch.setenv(
        "MI_API_KEYS", json.dumps({"operator-key": {"org_id": "ORG-9", "role": "operator"}})
    )
    monkeypatch.setattr(feedback_api, "with_pg", lambda _dsn: _Conn(calls))

    client = TestClient(app)
    response = client.post(
        "/api/v1/rca/feedback",
        json={
            "run_id": "RUN-1",
            "recommendation_id": "REC-1",
            "action": "accept",
            "asset_id": "ASSET-9",
        },
        headers={"X-API-Key": "operator-key"},
    )

    assert response.status_code == 200
    insert_call = next(params for query, params in calls if "INSERT INTO rca_feedback" in query)
    assert insert_call[3] == "ORG-9"
    assert insert_call[4] == "ASSET-9"


def test_outcomes_queries_are_org_scoped(monkeypatch):
    calls = []
    monkeypatch.setenv("MI_MULTI_TENANT", "true")
    monkeypatch.setenv("MI_AUTH_MODE", "api_key")
    monkeypatch.setenv(
        "MI_API_KEYS", json.dumps({"viewer-key": {"org_id": "ORG-1", "role": "viewer"}})
    )
    monkeypatch.setattr(outcomes_api, "with_pg", lambda _dsn: _Conn(calls))

    client = TestClient(app)
    response = client.get(
        "/api/v1/reports/rca-outcomes?window=30", headers={"X-API-Key": "viewer-key"}
    )

    assert response.status_code == 200
    relevant_calls = [
        (query, params)
        for query, params in calls
        if "FROM rca_feedback" in query or "FROM workorders" in query or "FROM events" in query
    ]
    assert relevant_calls
    assert all("org_id" in query for query, _ in relevant_calls)
    assert any("ORG-1" in params for _, params in relevant_calls)
