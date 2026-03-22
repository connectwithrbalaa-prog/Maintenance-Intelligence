import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import feedback as feedback_mod


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def execute(self, query, params):
        self.connection.executed.append((query, params))
        normalized = " ".join(query.split())
        if normalized.startswith("INSERT INTO rca_feedback"):
            self.rows = [
                (
                    params[0],
                    params[1],
                    params[2],
                    params[3],
                    params[4],
                    params[5],
                    json.loads(params[6]) if params[6] is not None else {},
                    params[7],
                    params[8],
                    datetime(2026, 3, 15, 11, 45, tzinfo=timezone.utc),
                )
            ]
            return
        if normalized.startswith("SELECT id, run_id, recommendation_id"):
            self.rows = list(self.connection.history_rows)
            return
        raise AssertionError(f"Unexpected SQL: {query}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, history_rows=None):
        self.executed = []
        self.history_rows = history_rows or []
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self.closed = True


def test_submit_feedback_enriches_from_run_summary_and_request_identity(monkeypatch, tmp_path):
    run_dir = tmp_path / "outputs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-123.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-123",
                "recommendation_id": "REC-123",
                "context_meta": {
                    "org_id": "demo-org",
                    "asset_id": "PUMP-101",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    fake_connection = FakeConnection()
    monkeypatch.setattr(feedback_mod, "connection_factory", lambda _dsn: fake_connection)

    client = TestClient(app)
    response = client.post(
        "/api/v1/rca/feedback",
        json={
            "run_id": "RUN-123",
            "action": "accept",
            "changes": {"title": "Keep recommendation"},
            "reason": "Matches field evidence",
        },
        headers={"x-user-id": "operator-7"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["feedback"]["run_id"] == "RUN-123"
    assert payload["feedback"]["recommendation_id"] == "REC-123"
    assert payload["feedback"]["org_id"] == "demo-org"
    assert payload["feedback"]["asset_id"] == "PUMP-101"
    assert payload["feedback"]["user_id"] == "operator-7"
    assert payload["feedback"]["changes"] == {"title": "Keep recommendation"}
    assert payload["feedback"]["created_at"] == "2026-03-15T11:45:00+00:00"
    assert fake_connection.closed is True

    insert_query, insert_params = fake_connection.executed[0]
    assert "INSERT INTO rca_feedback" in insert_query
    assert insert_params[1] == "RUN-123"
    assert insert_params[2] == "REC-123"
    assert insert_params[3] == "demo-org"
    assert insert_params[4] == "PUMP-101"
    assert insert_params[8] == "operator-7"


def test_submit_feedback_requires_recommendation_id_when_summary_missing(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    client = TestClient(app)

    response = client.post(
        "/api/v1/rca/feedback",
        json={
            "run_id": "RUN-MISSING",
            "action": "reject",
            "reason": "Insufficient context",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "recommendation_id is required"


def test_submit_feedback_rejects_read_only_role(monkeypatch, tmp_path):
    run_dir = tmp_path / "outputs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-123.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-123",
                "recommendation_id": "REC-123",
                "context_meta": {"org_id": "demo-org", "asset_id": "PUMP-101"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    client = TestClient(app)
    response = client.post(
        "/api/v1/rca/feedback",
        json={"run_id": "RUN-123", "action": "accept"},
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "Feedback submission requires planner, maintainer, or admin role"
    )


def test_submit_feedback_rejects_user_id_spoof(monkeypatch, tmp_path):
    run_dir = tmp_path / "outputs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-123.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-123",
                "recommendation_id": "REC-123",
                "context_meta": {"org_id": "demo-org", "asset_id": "PUMP-101"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    client = TestClient(app)
    response = client.post(
        "/api/v1/rca/feedback",
        json={"run_id": "RUN-123", "action": "accept", "user_id": "other-user"},
        headers={"x-user-id": "operator-7", "x-user-role": "planner"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Feedback actor must match authenticated identity"


def test_list_feedback_filters_by_run_and_action(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection(
        history_rows=[
            (
                "FB-2",
                "RUN-123",
                "REC-123",
                "demo-org",
                "PUMP-101",
                "accept",
                {"title": "Adjusted"},
                "Looks correct",
                "operator-1",
                datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
            ),
            (
                "FB-1",
                "RUN-123",
                "REC-123",
                "demo-org",
                "PUMP-101",
                "accept",
                {},
                None,
                "operator-2",
                datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    monkeypatch.setattr(feedback_mod, "connection_factory", lambda _dsn: fake_connection)

    client = TestClient(app)
    response = client.get(
        "/api/v1/rca/feedback?run_id=RUN-123&action=accept&limit=5",
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["feedback_id"] for item in payload] == ["FB-2", "FB-1"]
    assert payload[0]["changes"] == {"title": "Adjusted"}
    assert payload[1]["changes"] == {}
    assert payload[0]["created_at"] == "2026-03-15T12:00:00+00:00"
    assert fake_connection.closed is True

    select_query, select_params = fake_connection.executed[0]
    assert "WHERE run_id = %s AND action = %s" in select_query
    assert select_params == ("RUN-123", "accept", 5)


def test_list_feedback_requires_run_or_recommendation_filter(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    client = TestClient(app)

    response = client.get(
        "/api/v1/rca/feedback", headers={"x-user-id": "viewer-1", "x-user-role": "viewer"}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "run_id or recommendation_id is required"


def test_submit_feedback_rejects_cross_tenant_submission(monkeypatch, tmp_path):
    run_dir = tmp_path / "outputs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-123.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-123",
                "recommendation_id": "REC-123",
                "context_meta": {"org_id": "demo-org", "asset_id": "PUMP-101"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    client = TestClient(app)
    response = client.post(
        "/api/v1/rca/feedback",
        json={"run_id": "RUN-123", "action": "accept"},
        headers={"x-user-id": "planner-1", "x-user-role": "planner", "x-user-org": "other-org"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Feedback scope does not match authenticated tenant"


def test_list_feedback_requires_authenticated_identity(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    client = TestClient(app)

    response = client.get("/api/v1/rca/feedback")

    assert response.status_code == 403
    assert response.json()["detail"] == "Feedback history requires an authenticated identity"


def test_list_feedback_rejects_action_only_queries(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    client = TestClient(app)

    response = client.get(
        "/api/v1/rca/feedback?action=accept",
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "run_id or recommendation_id is required"
