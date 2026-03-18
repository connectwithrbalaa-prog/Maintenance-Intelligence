from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request

from maintenance_intelligence.runner.config import Settings


APPROVAL_ROLES = frozenset({"planner", "maintainer", "admin"})
ADMIN_ROLES = frozenset({"admin", "maintainer"})
DEMO_AUTH_MODES = frozenset({"demo", "dev-headers", "development"})


def _normalize_identity(user: Any) -> Optional[Dict[str, Any]]:
    if isinstance(user, dict):
        subject = user.get("subject") or user.get("sub") or user.get("user_id")
        if subject:
            return {"subject": subject, **user}
        return None
    if isinstance(user, str) and user:
        return {"subject": user}
    return None


def _auth_mode(settings: Settings) -> str:
    value = getattr(settings, "auth_mode", "demo")
    if isinstance(value, str):
        return value.strip().lower() or "demo"
    return "demo"


def _demo_header_auth_enabled(settings: Settings) -> bool:
    return bool(getattr(settings, "dev_allow_headers", False) and _auth_mode(settings) in DEMO_AUTH_MODES)


def resolve_identity(request: Request, settings: Optional[Settings] = None) -> Optional[Dict[str, Any]]:
    settings = settings or Settings()

    existing = _normalize_identity(getattr(request.state, "user", None))
    if existing:
        return existing

    if _demo_header_auth_enabled(settings):
        subject = request.headers.get("x-user-id") or request.headers.get("x-dev-user")
        if subject:
            role = request.headers.get("x-user-role") or "planner"
            identity = {"subject": subject, "role": role, "auth_source": "dev-header"}
            org_id = request.headers.get("x-org-id") or request.headers.get("x-user-org")
            site_id = request.headers.get("x-site-id") or request.headers.get("x-user-site")
            if org_id:
                identity["org_id"] = org_id
            if site_id:
                identity["site_id"] = site_id
            return identity

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


def get_identity_org_id(identity: Optional[Dict[str, Any]]) -> Optional[str]:
    normalized = _normalize_identity(identity)
    if not normalized:
        return None
    org_id = normalized.get("org_id")
    if isinstance(org_id, str):
        stripped = org_id.strip()
        return stripped or None
    return None


def get_identity_site_id(identity: Optional[Dict[str, Any]]) -> Optional[str]:
    normalized = _normalize_identity(identity)
    if not normalized:
        return None
    site_id = normalized.get("site_id")
    if isinstance(site_id, str):
        stripped = site_id.strip()
        return stripped or None
    return None


def identity_has_role(identity: Optional[Dict[str, Any]], allowed_roles: frozenset[str]) -> bool:
    role = get_identity_role(identity)
    return role in allowed_roles if role else False


def require_scoped_identity(
    request: Request,
    *,
    detail: str = "An authenticated identity is required",
    allowed_roles: Optional[frozenset[str]] = None,
    role_detail: Optional[str] = None,
    org_id: Optional[str] = None,
    site_id: Optional[str] = None,
    org_detail: str = "Authenticated identity is not authorized for this organization",
    site_detail: str = "Authenticated identity is not authorized for this site",
) -> Dict[str, Any]:
    identity = require_authenticated_identity(request, detail=detail)
    if allowed_roles and not identity_has_role(identity, allowed_roles):
        raise HTTPException(status_code=403, detail=role_detail or detail)
    identity_org_id = get_identity_org_id(identity)
    if org_id is not None and identity_org_id is not None and identity_org_id != org_id:
        raise HTTPException(status_code=403, detail=org_detail)
    identity_site_id = get_identity_site_id(identity)
    if site_id is not None and identity_site_id is not None and identity_site_id != site_id:
        raise HTTPException(status_code=403, detail=site_detail)
    return identity


def install_identity_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def identity_middleware(request: Request, call_next):
        request.state.user = resolve_identity(request)
        return await call_next(request)