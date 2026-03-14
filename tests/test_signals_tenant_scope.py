import json

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.context import assembler
from maintenance_intelligence.api import signals as signals_api


class _Cursor:
    def __init__(self, calls):
        self.calls = calls
        self.rows = []

    def execute(self, query, params=None):
        params = tuple(params or ())
        self.calls.append((query, params))
        normalized = " ".join(query.split())
        if "FROM signals" in normalized:
            self.rows = [("SIG-1", "vibration", 7.2, "mm/s", None, {"org_id": params[2] if len(params) > 2 else "ORG-A"})]
        elif "FROM signal_rollups" in normalized:
            self.rows = [("vibration", "1h", 7.2, 6.8, 8.1, {"org_id": params[2] if len(params) > 2 else "ORG-A"}, None)]
        elif "SELECT title FROM workorders" in normalized:
            self.rows = []
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


def test_signals_summary_api_scopes_queries_by_org(monkeypatch):
    calls = []
    monkeypatch.setenv("MI_MULTI_TENANT", "true")
    monkeypatch.setenv("MI_AUTH_MODE", "api_key")
    monkeypatch.setenv("MI_API_KEYS", json.dumps({"viewer-key": {"org_id": "ORG-A", "role": "viewer"}}))
    monkeypatch.setattr(signals_api, "with_pg", lambda _dsn: _Conn(calls))

    client = TestClient(app)
    response = client.get("/api/v1/signals/summary?asset_id=ASSET-1&limit=5", headers={"X-API-Key": "viewer-key"})

    assert response.status_code == 200
    relevant = [(query, params) for query, params in calls if "FROM signals" in query or "FROM signal_rollups" in query]
    assert relevant
    assert all("org_id = %s" in query for query, _ in relevant)
    assert all("ORG-A" in params for _, params in relevant)


def test_context_signal_queries_are_org_scoped(monkeypatch):
    calls = []
    monkeypatch.setenv("MI_MULTI_TENANT", "true")
    monkeypatch.setenv("MI_DEFAULT_ORG", "ORG-A")
    monkeypatch.setattr(assembler, "with_pg", lambda _dsn: _Conn(calls))

    ctx = assembler.get_event_context({"asset_id": "ASSET-1", "org_id": "ORG-A", "kind": "alarm"})

    assert ctx["asset_id"] == "ASSET-1"
    signal_queries = [(query, params) for query, params in calls if "FROM signals" in query or "FROM signal_rollups" in query]
    assert signal_queries
    assert all("org_id = %s" in query for query, _ in signal_queries)
    assert all("ORG-A" in params for _, params in signal_queries)