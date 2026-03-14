from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from maintenance_intelligence.api.auth import require_role
from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.multitenancy import TenantContext
from maintenance_intelligence.prompts.catalog import list_prompts, load_route_config, save_route_config
from maintenance_intelligence.runner.config import Settings


router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])


class PromptRouteConfigPayload(BaseModel):
    org_id: Optional[str] = Field(default=None, description="Optional org-specific override; omit for global")
    default_prompt_id: str
    canary_prompt_id: Optional[str] = None
    canary_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    auto_rollback_enabled: bool = True
    rollback_min_runs: int = Field(default=20, ge=1)
    rollback_acceptance_delta: float = Field(default=0.05, ge=0.0, le=1.0)


@router.get("")
def get_prompts(
    route: Optional[str] = Query(default=None),
    access: TenantContext = Depends(require_role("viewer")),
) -> Dict[str, Any]:
    settings = Settings()
    conn = with_pg(settings.pg_dsn)
    try:
        prompts = list_prompts(conn, route_name=route)
        configs = {}
        if route:
            configs["effective"] = load_route_config(conn, settings, route, access.org_id)
        return {"prompts": prompts, "configs": configs}
    finally:
        conn.close()


@router.put("/routes/{route_name}")
def put_prompt_route_config(
    route_name: str,
    payload: PromptRouteConfigPayload,
    access: TenantContext = Depends(require_role("admin")),
) -> Dict[str, Any]:
    settings = Settings()
    conn = with_pg(settings.pg_dsn)
    try:
        saved = save_route_config(conn, route_name, payload.org_id, payload.model_dump())
        return {"status": "ok", "config": saved, "actor_org_id": access.org_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prompt config update failed: {exc}") from exc
    finally:
        conn.close()