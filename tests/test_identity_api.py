from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app


def test_whoami_returns_unauthenticated_by_default(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/whoami")

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is False
    assert payload["user"] is None


def test_whoami_uses_dev_headers_when_enabled(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    client = TestClient(app)
    response = client.get("/api/v1/whoami", headers={"x-user-id": "dev-user"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"]["subject"] == "dev-user"
    assert payload["user"]["auth_source"] == "dev-header"