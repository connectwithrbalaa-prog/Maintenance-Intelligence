from maintenance_intelligence.api.reports import router as reports_router
from maintenance_intelligence.api.health import router as health_router
from maintenance_intelligence.api.identity import router as identity_router
from maintenance_intelligence.api.middleware.identity import install_identity_middleware
from maintenance_intelligence.api.signals import router as signals_router
from maintenance_intelligence.api.metrics import router as metrics_router
from maintenance_intelligence.api.feedback import router as feedback_router
from maintenance_intelligence.api.outcomes import router as outcomes_router
from maintenance_intelligence.api.pm_advisor import router as pm_advisor_router
from maintenance_intelligence.api.portal import router as portal_router, WEB_DIR
from maintenance_intelligence.api.otel import init_tracing
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from maintenance_intelligence.runner.core import run
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.logging import setup_logger

app = FastAPI(title="Maintenance Intelligence API", version="0.1.0")
install_identity_middleware(app)
app.include_router(health_router)
app.include_router(identity_router)
app.include_router(reports_router)
app.include_router(signals_router)
app.include_router(feedback_router)
app.include_router(outcomes_router)
app.include_router(pm_advisor_router)
app.include_router(metrics_router)
app.include_router(portal_router)
app.mount("/portal/assets", StaticFiles(directory=WEB_DIR / "assets"), name="portal-assets")
settings = Settings()
setup_logger(settings.log_level)
init_tracing("maintenance-intelligence-api")

class TriggerPayload(BaseModel):
    event_id: str

@app.post("/api/v1/agents/rca/trigger")
def trigger_rca(p: TriggerPayload):
    return run(p.event_id, settings)
