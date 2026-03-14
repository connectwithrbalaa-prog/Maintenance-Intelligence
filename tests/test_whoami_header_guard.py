import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_intelligence.api.main import app


def test_whoami_header_guard_enabled(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "yes")
    client = TestClient(app)

    response = client.get(
        "/api/v1/whoami",
        headers={"X-Org-Id": "org-guard", "X-Role": "viewer", "X-Subject": "guard-user"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "org_id": "org-guard",
        "role": "viewer",
        "subject": "guard-user",
    }


def test_whoami_header_guard_disabled(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    client = TestClient(app)

    response = client.get(
        "/api/v1/whoami",
        headers={"X-Org-Id": "org-guard", "X-Role": "viewer", "X-Subject": "guard-user"},
    )

    assert response.status_code == 200
    assert response.json() == {"org_id": None, "role": None, "subject": None}