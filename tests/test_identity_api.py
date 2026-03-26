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


def test_whoami_uses_trusted_forwarded_headers_when_enabled(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    monkeypatch.setenv("MI_AUTH_TRUST_FORWARDED_HEADERS", "true")

    client = TestClient(app)
    response = client.get(
        "/api/v1/whoami",
        headers={
            "x-auth-request-user": "proxy-user",
            "x-auth-request-role": "planner,admin",
            "x-auth-request-org": "ORG-1",
            "x-auth-request-sites": "SITE-A,SITE-B",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"]["subject"] == "proxy-user"
    assert payload["user"]["auth_source"] == "trusted-header"
    assert payload["user"]["org_id"] == "ORG-1"
    assert payload["user"]["roles"] == ["planner", "admin"]


def test_whoami_ignores_bearer_token_when_jwks_not_configured(monkeypatch):
    """Without MI_AUTH_JWT_JWKS_URL, a Bearer token must be silently ignored
    and the request treated as unauthenticated."""
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    monkeypatch.delenv("MI_AUTH_JWT_JWKS_URL", raising=False)

    client = TestClient(app)
    response = client.get(
        "/api/v1/whoami",
        headers={"Authorization": "Bearer some.jwt.token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is False


def test_whoami_reports_jwt_bearer_source_when_jwks_configured(monkeypatch):
    """Unit test: _jwt_bearer_identity extracts claims from a decoded token and
    returns an identity dict with auth_source='jwt-bearer'.

    Tested directly (no HTTP stack) so it is not affected by the module-cache
    clearing that test_pm_proposals_api performs."""
    import importlib
    from unittest.mock import patch
    import jwt as pyjwt_module

    # Always import the live module — importlib.import_module goes through the
    # current sys.modules cache, giving us the same object the app middleware uses.
    mid = importlib.import_module("maintenance_intelligence.api.middleware.identity")

    settings = importlib.import_module(
        "maintenance_intelligence.runner.config"
    ).Settings.model_construct(
        auth_jwt_jwks_url="https://example.com/.well-known/jwks.json",
        auth_jwt_algorithms="RS256",
        auth_jwt_leeway_s=30,
        auth_jwt_audience=None,
        auth_jwt_issuer=None,
        auth_jwt_org_claim="org_id",
        auth_jwt_roles_claim="roles",
        auth_jwt_sites_claim="site_ids",
        dev_allow_headers=False,
        auth_trust_forwarded_headers=False,
    )

    class _Headers:
        def get(self, key, default=""):
            return "Bearer fake.jwt.token" if key == "authorization" else default

    class _FakeRequest:
        headers = _Headers()

    class _FakeSigningKey:
        key = object()

    class _FakeJWKSClient:
        def get_signing_key_from_jwt(self, _token):
            return _FakeSigningKey()

    def _fake_decode(_token, _key, **_kwargs):
        return {"sub": "jwt-user-123", "org_id": "ORG-JWT", "roles": ["admin"]}

    orig_clients = dict(mid._jwks_clients)
    mid._jwks_clients["https://example.com/.well-known/jwks.json"] = _FakeJWKSClient()
    try:
        with patch.object(pyjwt_module, "decode", _fake_decode):
            result = mid._jwt_bearer_identity(_FakeRequest(), settings)
    finally:
        mid._jwks_clients.clear()
        mid._jwks_clients.update(orig_clients)

    assert result is not None
    assert result["subject"] == "jwt-user-123"
    assert result["auth_source"] == "jwt-bearer"
    assert result["org_id"] == "ORG-JWT"

