from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request

from maintenance_intelligence.runner.config import Settings

APPROVAL_ROLES = frozenset({"planner", "maintainer", "admin"})
ADMIN_ROLES = frozenset({"admin", "maintainer"})


def _normalize_identity(user: Any) -> Optional[Dict[str, Any]]:
    if isinstance(user, dict):
        subject = user.get("subject") or user.get("sub") or user.get("user_id")
        if subject:
            return {"subject": subject, **user}
        return None
    if isinstance(user, str) and user:
        return {"subject": user}
    return None


def resolve_identity(
    request: Request, settings: Optional[Settings] = None
) -> Optional[Dict[str, Any]]:
    settings = settings or Settings()

    existing = _normalize_identity(getattr(request.state, "user", None))
    if existing:
        return existing

    if settings.dev_allow_headers:
        subject = request.headers.get("x-user-id") or request.headers.get("x-dev-user")
        if subject:
            role = request.headers.get("x-user-role") or "planner"
            return {"subject": subject, "role": role, "auth_source": "dev-header"}

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


def identity_has_role(identity: Optional[Dict[str, Any]], allowed_roles: frozenset[str]) -> bool:
    role = get_identity_role(identity)
    return role in allowed_roles if role else False


def install_identity_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def identity_middleware(request: Request, call_next):
        request.state.user = resolve_identity(request)
        return await call_next(request)
