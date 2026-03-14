from typing import Callable

from fastapi import Depends, Header, HTTPException

from maintenance_intelligence.multitenancy import TenantContext, normalize_role, resolve_org_id, role_allows
from maintenance_intelligence.runner.config import Settings


def _context_from_api_key(api_key: str, settings: Settings) -> TenantContext:
    payload = settings.api_keys.get(api_key)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=403, detail="Invalid API key")
    org_id = payload.get("org_id")
    role = payload.get("role")
    if not org_id or not role:
        raise HTTPException(status_code=500, detail="API key configuration incomplete")
    try:
        role = normalize_role(role)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return TenantContext(org_id=str(org_id), role=role, subject="api_key")


def get_request_context(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> TenantContext:
    settings = Settings()
    auth_mode = (settings.auth_mode or "none").strip().lower()
    if auth_mode == "none":
        return TenantContext(org_id=resolve_org_id(settings), role="admin", subject="anonymous")
    if auth_mode != "api_key":
        raise HTTPException(status_code=500, detail="Unsupported auth mode")
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return _context_from_api_key(x_api_key, settings)


def require_role(minimum_role: str) -> Callable:
    minimum_role = normalize_role(minimum_role)

    def dependency(access: TenantContext = Depends(get_request_context)) -> TenantContext:
        if not role_allows(access.role, minimum_role):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return access

    return dependency