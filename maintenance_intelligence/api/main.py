from maintenance_intelligence.api.reports import router as reports_router
from maintenance_intelligence.api.repair_plan import router as repair_plan_router
from maintenance_intelligence.api.health import router as health_router
from maintenance_intelligence.api.identity import router as identity_router
from maintenance_intelligence.api.middleware.identity import (
    APPROVAL_ROLES,
    get_identity,
    get_identity_role,
    get_identity_subject,
    install_identity_middleware,
    require_identity_scope,
)
from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.api.signals import router as signals_router
from maintenance_intelligence.api.metrics import router as metrics_router
from maintenance_intelligence.api.feedback import router as feedback_router
from maintenance_intelligence.api.outcomes import router as outcomes_router
from maintenance_intelligence.api.pm_advisor import router as pm_advisor_router
from maintenance_intelligence.api.portal import router as portal_router, WEB_DIR
from maintenance_intelligence.api.hierarchy import router as hierarchy_router
from maintenance_intelligence.api.taxonomy import router as taxonomy_router
from maintenance_intelligence.api.failure_events import router as failure_events_router
from maintenance_intelligence.api.reliability import router as reliability_router
from maintenance_intelligence.api.rag_context import router as rag_context_router
from maintenance_intelligence.api.connectors import router as connectors_router
from maintenance_intelligence.api.otel import init_tracing
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from maintenance_intelligence.runner.core import run
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.logging import setup_logger

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
app.include_router(hierarchy_router)
app.include_router(taxonomy_router)
app.include_router(failure_events_router)
app.include_router(reliability_router)
app.include_router(rag_context_router)
app.include_router(connectors_router)
app.include_router(portal_router)
assets_dir = WEB_DIR / "assets"
if assets_dir.exists():
    app.mount("/portal/assets", StaticFiles(directory=assets_dir), name="portal-assets")
settings = Settings()
setup_logger(settings.log_level)
init_tracing("maintenance-intelligence-api")


class TriggerPayload(BaseModel):
    event_id: str


def _load_event_scope(event_id: str) -> dict[str, str | None]:
    try:
        conn = with_pg(settings.pg_dsn)
    except Exception:
        return {"org_id": None}
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT org_id FROM events WHERE event_id = %s ORDER BY occurred_at DESC LIMIT 1",
                (event_id,),
            )
            row = cur.fetchone()
        return {"org_id": row[0] if row else None}
    except Exception:
        return {"org_id": None}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _require_trigger_access(request: Request) -> str:
    identity = get_identity(request)
    actor_id = get_identity_subject(identity) if identity else None
    actor_role = get_identity_role(identity) if identity else None
    if actor_id is None:
        raise HTTPException(
            status_code=403, detail="RCA trigger requires an authenticated identity"
        )
    if actor_role not in APPROVAL_ROLES:
        raise HTTPException(
            status_code=403, detail="RCA trigger requires planner, maintainer, or admin role"
        )
    return actor_id


@app.post("/api/v1/agents/rca/trigger")
def trigger_rca(p: TriggerPayload, request: Request):
    _require_trigger_access(request)
    event_scope = _load_event_scope(p.event_id)
    if event_scope.get("org_id"):
        require_identity_scope(
            request,
            org_id=event_scope.get("org_id"),
            detail="RCA trigger scope does not match authenticated tenant",
        )
    return run(p.event_id, settings)
