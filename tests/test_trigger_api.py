from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import main as main_mod


def test_trigger_requires_allowed_role(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    client = TestClient(app)

    response = client.post(
        "/api/v1/agents/rca/trigger",
        json={"event_id": "EV-123"},
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "RCA trigger requires planner, maintainer, or admin role"


def test_trigger_runs_for_allowed_role(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(
        main_mod,
        "run",
        lambda event_id, settings: {
            "run_id": "RUN-TRIGGER",
            "status": "ok",
            "recommendation_id": f"REC-{event_id}",
        },
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/agents/rca/trigger",
        json={"event_id": "EV-123"},
        headers={"x-user-id": "planner-1", "x-user-role": "planner"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "RUN-TRIGGER",
        "status": "ok",
        "recommendation_id": "REC-EV-123",
    }
