from maintenance_intelligence.api.reports import router as reports_router
from maintenance_intelligence.api.repair_plan import router as repair_plan_router
from maintenance_intelligence.api.health import router as health_router
from maintenance_intelligence.api.identity import router as identity_router
from maintenance_intelligence.api.middleware.identity import APPROVAL_ROLES, get_identity_role, get_identity_subject, install_identity_middleware, require_scoped_identity
from maintenance_intelligence.api.signals import router as signals_router
from maintenance_intelligence.api.metrics import router as metrics_router
from maintenance_intelligence.api.feedback import router as feedback_router
from maintenance_intelligence.api.outcomes import router as outcomes_router
from maintenance_intelligence.api.pm_advisor import router as pm_advisor_router
from maintenance_intelligence.api.portal import router as portal_router, WEB_DIR
from maintenance_intelligence.api.otel import init_tracing
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from maintenance_intelligence.runner.core import run
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.logging import setup_logger


def _mount_portal_assets(application: FastAPI) -> None:
    assets_dir = WEB_DIR / "assets"
    if assets_dir.is_dir():
        application.mount("/portal/assets", StaticFiles(directory=assets_dir), name="portal-assets")


app = FastAPI(title="Maintenance Intelligence API", version="0.1.0")
install_identity_middleware(app)
app.include_router(health_router)
app.include_router(repair_plan_router)
app.include_router(identity_router)
app.include_router(reports_router)
app.include_router(signals_router)
app.include_router(feedback_router)
app.include_router(outcomes_router)
app.include_router(pm_advisor_router)
app.include_router(metrics_router)
app.include_router(portal_router)
_mount_portal_assets(app)
settings = Settings()
setup_logger(settings.log_level)
init_tracing("maintenance-intelligence-api")

class TriggerPayload(BaseModel):
    event_id: str


def _require_trigger_access(request: Request) -> str:
    identity = require_scoped_identity(
        request,
        detail="RCA trigger requires an authenticated identity",
        allowed_roles=APPROVAL_ROLES,
        role_detail="RCA trigger requires planner, maintainer, or admin role",
    )
    actor_id = get_identity_subject(identity)
    actor_role = get_identity_role(identity)
    if actor_id is None or actor_role is None:
        raise HTTPException(status_code=403, detail="RCA trigger requires an authenticated identity")
    return actor_id

@app.post("/api/v1/agents/rca/trigger")
def trigger_rca(p: TriggerPayload, request: Request):
    _require_trigger_access(request)
    return run(p.event_id, settings)
