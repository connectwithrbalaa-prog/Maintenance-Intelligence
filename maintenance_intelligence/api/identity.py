from fastapi import APIRouter, Request

from maintenance_intelligence.api.middleware.identity import get_identity

router = APIRouter(prefix="/api/v1", tags=["identity"])


@router.get("/whoami")
def whoami(request: Request):
    identity = get_identity(request)
    return {
        "authenticated": identity is not None,
        "user": identity,
    }