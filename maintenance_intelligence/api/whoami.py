from fastapi import APIRouter, Header, Request

from maintenance_intelligence.api.auth import get_request_context
from maintenance_intelligence.multitenancy import TenantContext, normalize_role
from maintenance_intelligence.runner.config import Settings

router = APIRouter(prefix="/api/v1", tags=["auth"])


def _header_fallback(
    x_org_id: str | None,
    x_role: str | None,
    x_subject: str | None,
) -> TenantContext:
    settings = Settings()
    role = normalize_role((x_role or "admin").strip().lower())
    return TenantContext(
        org_id=(x_org_id or settings.default_org).strip(),
        role=role,
        subject=(x_subject or "dev-header").strip(),
    )


def _dev_headers_allowed() -> bool:
    return bool(Settings().dev_allow_headers)


def resolve_request_identity(
    request: Request,
    x_api_key: str | None = None,
    x_org_id: str | None = None,
    x_role: str | None = None,
    x_subject: str | None = None,
    allow_missing: bool = False,
) -> TenantContext | None:
    user = getattr(request.state, "user", None)
    if isinstance(user, TenantContext):
        return user
    if user and hasattr(user, "org_id") and hasattr(user, "role"):
        return TenantContext(
            org_id=str(getattr(user, "org_id")),
            role=normalize_role(str(getattr(user, "role"))),
            subject=str(getattr(user, "subject", "request-state")),
        )
    if x_org_id or x_role or x_subject:
        if _dev_headers_allowed():
            return _header_fallback(x_org_id, x_role, x_subject)
        return None
    return get_request_context(x_api_key=x_api_key)


@router.get("/whoami")
def whoami(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    x_role: str | None = Header(default=None, alias="X-Role"),
    x_subject: str | None = Header(default=None, alias="X-Subject"),
):
    access = resolve_request_identity(
        request,
        x_api_key=x_api_key,
        x_org_id=x_org_id,
        x_role=x_role,
        x_subject=x_subject,
        allow_missing=True,
    )
    if access is None:
        return {"org_id": None, "role": None, "subject": None}
    return {"org_id": access.org_id, "role": access.role, "subject": access.subject}