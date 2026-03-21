import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api.whoami import router as whoami_router
from maintenance_intelligence.multitenancy import TenantContext


def test_whoami_header_fallback():
    client = TestClient(app)
    import os

    os.environ["MI_DEV_ALLOW_HEADERS"] = "true"
    try:
        response = client.get(
            "/api/v1/whoami",
            headers={
                "X-Org-Id": "org-demo",
                "X-Role": "operator",
                "X-Subject": "portal-user",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "org_id": "org-demo",
            "role": "operator",
            "subject": "portal-user",
        }
    finally:
        os.environ.pop("MI_DEV_ALLOW_HEADERS", None)


def test_whoami_header_fallback_disabled_returns_null(monkeypatch):
    client = TestClient(app)
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)

    response = client.get(
        "/api/v1/whoami",
        headers={
            "X-Org-Id": "org-demo",
            "X-Role": "operator",
            "X-Subject": "portal-user",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"org_id": None, "role": None, "subject": None}


def test_whoami_request_state_user():
    class InjectUserMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = TenantContext(
                org_id="org-state", role="viewer", subject="state-user"
            )
            return await call_next(request)

    temp_app = FastAPI()
    temp_app.add_middleware(InjectUserMiddleware)
    temp_app.include_router(whoami_router)

    client = TestClient(temp_app)
    response = client.get(
        "/api/v1/whoami",
        headers={"X-Org-Id": "org-demo", "X-Role": "operator", "X-Subject": "portal-user"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "org_id": "org-state",
        "role": "viewer",
        "subject": "state-user",
    }