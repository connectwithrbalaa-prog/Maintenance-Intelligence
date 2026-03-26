from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request

from maintenance_intelligence.runner.config import Settings

# Module-level JWKS client cache keyed by JWKS URL.
# PyJWKClient handles key rotation internally; we cache the client to avoid
# re-instantiating on every request.
_jwks_clients: Dict[str, Any] = {}

APPROVAL_ROLES = frozenset({"planner", "maintainer", "admin"})
ADMIN_ROLES = frozenset({"admin", "maintainer"})


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _parse_csv_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            text = _as_text(item)
            if text:
                out.append(text)
        return out
    text = _as_text(value)
    return [text] if text else []


def _normalize_identity(user: Any) -> Optional[Dict[str, Any]]:
    if isinstance(user, dict):
        subject = user.get("subject") or user.get("sub") or user.get("user_id")
        if subject:
            normalized = {"subject": subject, **user}
            role = _as_text(normalized.get("role"))
            roles = _parse_csv_text(normalized.get("roles") or role)
            if roles:
                normalized["roles"] = [item.lower() for item in roles]
                normalized["role"] = normalized["roles"][0]
            org_id = _as_text(normalized.get("org_id")) or _as_text(normalized.get("org"))
            if org_id is not None:
                normalized["org_id"] = org_id
            site_id = _as_text(normalized.get("site_id")) or _as_text(normalized.get("site"))
            site_ids = _parse_csv_text(normalized.get("site_ids") or normalized.get("sites"))
            if site_id and site_id not in site_ids:
                site_ids = [site_id, *site_ids]
            if site_id is not None:
                normalized["site_id"] = site_id
            if site_ids:
                normalized["site_ids"] = site_ids
            return normalized
        return None
    if isinstance(user, str) and user:
        return {"subject": user}
    return None


def _trusted_header_identity(request: Request, settings: Settings) -> Optional[Dict[str, Any]]:
    if not settings.auth_trust_forwarded_headers:
        return None
    subject = request.headers.get(settings.auth_subject_header)
    if not subject:
        return None
    roles = _parse_csv_text(request.headers.get(settings.auth_role_header))
    org_id = _as_text(request.headers.get(settings.auth_org_header))
    site_id = _as_text(request.headers.get(settings.auth_site_header))
    site_ids = _parse_csv_text(request.headers.get(settings.auth_sites_header))
    if site_id and site_id not in site_ids:
        site_ids = [site_id, *site_ids]
    identity: Dict[str, Any] = {
        "subject": subject,
        "auth_source": "trusted-header",
        "org_id": org_id,
        "site_id": site_id,
        "site_ids": site_ids,
    }
    if roles:
        identity["roles"] = [item.lower() for item in roles]
        identity["role"] = identity["roles"][0]
    return identity


def _dev_header_identity(request: Request, settings: Settings) -> Optional[Dict[str, Any]]:
    if not settings.dev_allow_headers:
        return None
    subject = request.headers.get("x-user-id") or request.headers.get("x-dev-user")
    if not subject:
        return None
    roles = _parse_csv_text(request.headers.get("x-user-role") or "planner")
    org_id = _as_text(request.headers.get("x-user-org"))
    site_id = _as_text(request.headers.get("x-user-site"))
    site_ids = _parse_csv_text(request.headers.get("x-user-sites"))
    if site_id and site_id not in site_ids:
        site_ids = [site_id, *site_ids]
    return {
        "subject": subject,
        "role": roles[0].lower() if roles else "planner",
        "roles": [item.lower() for item in roles] if roles else ["planner"],
        "org_id": org_id,
        "site_id": site_id,
        "site_ids": site_ids,
        "auth_source": "dev-header",
    }


def _jwt_bearer_identity(request: Request, settings: Settings) -> Optional[Dict[str, Any]]:
    """Validate a Bearer JWT token against the configured JWKS endpoint.

    Returns a normalised identity dict with ``auth_source="jwt-bearer"`` on
    success, or ``None`` when the header is absent, JWKS is not configured, or
    token validation fails.
    """
    if not settings.auth_jwt_jwks_url:
        return None
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None
    try:
        import jwt  # PyJWT
        from jwt import PyJWKClient

        jwks_url = settings.auth_jwt_jwks_url
        if jwks_url not in _jwks_clients:
            _jwks_clients[jwks_url] = PyJWKClient(jwks_url, cache_keys=True, lifespan=300)
        client = _jwks_clients[jwks_url]
        signing_key = client.get_signing_key_from_jwt(token)
        algorithms = [a.strip() for a in settings.auth_jwt_algorithms.split(",") if a.strip()]
        decode_kwargs: Dict[str, Any] = {"algorithms": algorithms, "leeway": settings.auth_jwt_leeway_s}
        if settings.auth_jwt_audience:
            decode_kwargs["audience"] = settings.auth_jwt_audience
        if settings.auth_jwt_issuer:
            decode_kwargs["issuer"] = settings.auth_jwt_issuer
        claims: Dict[str, Any] = jwt.decode(token, signing_key.key, **decode_kwargs)
    except Exception:
        # Any validation failure (expired, bad sig, wrong audience, etc.) is
        # treated as unauthenticated rather than a hard error.
        return None

    subject = _as_text(claims.get("sub"))
    if not subject:
        return None

    roles = _parse_csv_text(
        claims.get(settings.auth_jwt_roles_claim) or claims.get("role")
    )
    org_id = _as_text(
        claims.get(settings.auth_jwt_org_claim)
        or claims.get("org")
        or claims.get("tenant_id")
    )
    site_id = _as_text(claims.get("site_id") or claims.get("site"))
    site_ids = _parse_csv_text(
        claims.get(settings.auth_jwt_sites_claim) or claims.get("site_ids")
    )
    if site_id and site_id not in site_ids:
        site_ids = [site_id, *site_ids]

    identity: Dict[str, Any] = {
        "subject": subject,
        "auth_source": "jwt-bearer",
        "org_id": org_id,
        "site_id": site_id,
        "site_ids": site_ids,
    }
    if roles:
        identity["roles"] = [r.lower() for r in roles]
        identity["role"] = identity["roles"][0]
    return identity


def resolve_identity(
    request: Request, settings: Optional[Settings] = None
) -> Optional[Dict[str, Any]]:
    settings = settings or Settings()

    existing = _normalize_identity(getattr(request.state, "user", None))
    if existing:
        return existing

    # JWT bearer takes priority over proxy-forwarded headers.
    jwt_identity = _jwt_bearer_identity(request, settings)
    if jwt_identity:
        return _normalize_identity(jwt_identity)

    trusted = _trusted_header_identity(request, settings)
    if trusted:
        return _normalize_identity(trusted)

    dev_identity = _dev_header_identity(request, settings)
    if dev_identity:
        return _normalize_identity(dev_identity)

    return None


def get_identity(request: Request) -> Optional[Dict[str, Any]]:
    return _normalize_identity(getattr(request.state, "user", None))


def require_authenticated_identity(
    request: Request,
    *,
    detail: str = "An authenticated identity is required",
) -> Dict[str, Any]:
    identity = get_identity(request)
    if get_identity_subject(identity) is None:
        raise HTTPException(status_code=403, detail=detail)
    return identity or {}


def get_identity_subject(identity: Optional[Dict[str, Any]]) -> Optional[str]:
    return _normalize_identity(identity).get("subject") if _normalize_identity(identity) else None


def get_identity_role(identity: Optional[Dict[str, Any]]) -> Optional[str]:
    normalized = _normalize_identity(identity)
    if not normalized:
        return None
    role = normalized.get("role")
    if isinstance(role, str):
        stripped = role.strip().lower()
        return stripped or None
    return None


def get_identity_roles(identity: Optional[Dict[str, Any]]) -> list[str]:
    normalized = _normalize_identity(identity)
    if not normalized:
        return []
    roles = _parse_csv_text(normalized.get("roles"))
    if roles:
        return [item.lower() for item in roles]
    role = get_identity_role(normalized)
    return [role] if role else []


def get_identity_org_id(identity: Optional[Dict[str, Any]]) -> Optional[str]:
    normalized = _normalize_identity(identity)
    return _as_text(normalized.get("org_id")) if normalized else None


def get_identity_site_ids(identity: Optional[Dict[str, Any]]) -> list[str]:
    normalized = _normalize_identity(identity)
    if not normalized:
        return []
    site_id = _as_text(normalized.get("site_id"))
    site_ids = _parse_csv_text(normalized.get("site_ids"))
    if site_id and site_id not in site_ids:
        site_ids = [site_id, *site_ids]
    return site_ids


def identity_has_role(identity: Optional[Dict[str, Any]], allowed_roles: frozenset[str]) -> bool:
    return any(role in allowed_roles for role in get_identity_roles(identity))


def identity_matches_scope(
    identity: Optional[Dict[str, Any]],
    *,
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> bool:
    normalized = _normalize_identity(identity)
    if normalized is None:
        return False
    settings = settings or Settings()
    actor_org_id = get_identity_org_id(normalized)
    actor_site_ids = get_identity_site_ids(normalized)
    # The dev bypass is intentionally narrow: it only applies when the identity
    # originates from a dev header (auth_source=="dev-header") AND the dev
    # header mode is explicitly enabled.  Trusted-proxy and JWT identities must
    # always carry org/site claims.
    is_dev_source = (
        settings.dev_allow_headers
        and (normalized or {}).get("auth_source") == "dev-header"
    )
    if org_id:
        if actor_org_id:
            if actor_org_id != org_id:
                return False
        elif not is_dev_source:
            return False
    if site_id:
        if actor_site_ids:
            if site_id not in actor_site_ids:
                return False
        elif not is_dev_source:
            return False
    return True


def require_identity_scope(
    request: Request,
    *,
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    detail: str = "Authenticated identity does not have access to this tenant scope",
) -> Dict[str, Any]:
    settings = Settings()
    identity = require_authenticated_identity(request, detail=detail)
    if not identity_matches_scope(identity, org_id=org_id, site_id=site_id, settings=settings):
        raise HTTPException(status_code=403, detail=detail)
    return identity


def install_identity_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def identity_middleware(request: Request, call_next):
        request.state.user = resolve_identity(request)
        return await call_next(request)
