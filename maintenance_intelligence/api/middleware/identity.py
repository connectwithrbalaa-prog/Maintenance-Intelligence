from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request

from maintenance_intelligence.runner.config import Settings


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


def install_identity_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def identity_middleware(request: Request, call_next):
        request.state.user = resolve_identity(request)
        return await call_next(request)
