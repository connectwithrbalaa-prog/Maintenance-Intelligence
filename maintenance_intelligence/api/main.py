from fastapi import Depends, FastAPI
from pydantic import BaseModel

from maintenance_intelligence.api.auth import require_role
from maintenance_intelligence.api.reports import router as reports_router
from maintenance_intelligence.api.health import router as health_router
from maintenance_intelligence.api.signals import router as signals_router
from maintenance_intelligence.api.metrics import router as metrics_router
from maintenance_intelligence.api.feedback import router as feedback_router
from maintenance_intelligence.api.outcomes import router as outcomes_router
from maintenance_intelligence.api.otel import init_tracing
from maintenance_intelligence.runner.core import run
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.logging import setup_logger
from maintenance_intelligence.multitenancy import TenantContext

app = FastAPI(title="Maintenance Intelligence API", version="0.1.0")
app.include_router(health_router)
app.include_router(reports_router)
app.include_router(signals_router)
app.include_router(feedback_router)
app.include_router(outcomes_router)
app.include_router(metrics_router)
settings = Settings()
setup_logger(settings.log_level)
init_tracing("maintenance-intelligence-api")

class TriggerPayload(BaseModel):
    event_id: str

@app.post("/api/v1/agents/rca/trigger")
def trigger_rca(p: TriggerPayload, access: TenantContext = Depends(require_role("operator"))):
    return run(p.event_id, Settings(), org_id=access.org_id)
