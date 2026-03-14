import json

from fastapi.testclient import TestClient

from maintenance_intelligence.api import feedback as feedback_api
from maintenance_intelligence.api import prompts as prompts_api
from maintenance_intelligence.api.main import app
from maintenance_intelligence.api.metrics import prompt_feedback_total


def test_prompt_api_list_and_admin_update(monkeypatch):
    monkeypatch.setenv("MI_AUTH_MODE", "api_key")
    monkeypatch.setenv(
        "MI_API_KEYS",
        json.dumps(
            {
                "viewer-key": {"org_id": "ORG-1", "role": "viewer"},
                "admin-key": {"org_id": "ORG-1", "role": "admin"},
            }
        ),
    )

    class FakeConn:
        def close(self):
            return None

    monkeypatch.setattr(prompts_api, "with_pg", lambda _dsn: FakeConn())
    monkeypatch.setattr(
        prompts_api,
        "list_prompts",
        lambda conn, route_name=None: [{"prompt_id": "rca-default-v1", "route_name": route_name or "rca"}],
    )
    monkeypatch.setattr(
        prompts_api,
        "load_route_config",
        lambda conn, settings, route_name, org_id: {"route_name": route_name, "default_prompt_id": "rca-default-v1", "org_id": org_id},
    )
    monkeypatch.setattr(
        prompts_api,
        "save_route_config",
        lambda conn, route_name, org_id, payload: {"route_name": route_name, "org_id": org_id, **payload},
    )

    client = TestClient(app)
    listed = client.get("/api/v1/prompts?route=rca", headers={"X-API-Key": "viewer-key"})
    updated = client.put(
        "/api/v1/prompts/routes/rca",
        json={"default_prompt_id": "rca-default-v1", "canary_prompt_id": "rca-canary-v1", "canary_ratio": 0.1},
        headers={"X-API-Key": "admin-key"},
    )
    denied = client.put(
        "/api/v1/prompts/routes/rca",
        json={"default_prompt_id": "rca-default-v1"},
        headers={"X-API-Key": "viewer-key"},
    )

    assert listed.status_code == 200
    assert listed.json()["prompts"][0]["prompt_id"] == "rca-default-v1"
    assert updated.status_code == 200
    assert updated.json()["config"]["canary_prompt_id"] == "rca-canary-v1"
    assert denied.status_code == 403


def test_feedback_prompt_metric_increments(monkeypatch):
    monkeypatch.setenv("MI_AUTH_MODE", "api_key")
    monkeypatch.setenv("MI_API_KEYS", json.dumps({"operator-key": {"org_id": "ORG-1", "role": "operator"}}))

    class FakeCursor:
        def execute(self, *_args, **_kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConn:
        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def close(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(feedback_api, "with_pg", lambda _dsn: FakeConn())

    client = TestClient(app)
    before = prompt_feedback_total.labels(route="rca", prompt_id="rca-default-v1", action="accept")._value.get()
    response = client.post(
        "/api/v1/rca/feedback",
        json={
            "run_id": "RUN-1",
            "recommendation_id": "REC-1",
            "action": "accept",
            "prompt_id": "rca-default-v1",
            "prompt_route": "rca",
        },
        headers={"X-API-Key": "operator-key"},
    )
    after = prompt_feedback_total.labels(route="rca", prompt_id="rca-default-v1", action="accept")._value.get()

    assert response.status_code == 200
    assert after == before + 1