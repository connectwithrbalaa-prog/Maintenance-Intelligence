from maintenance_intelligence.api.health import router as health_router
from fastapi import FastAPI
from pydantic import BaseModel
from maintenance_intelligence.runner.core import run
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.logging import setup_logger

app = FastAPI(title="Maintenance Intelligence API", version="0.1.0")\napp.include_router(health_router)
settings = Settings()
setup_logger(settings.log_level)

class TriggerPayload(BaseModel):
    event_id: str

@app.post("/api/v1/agents/rca/trigger")
def trigger_rca(p: TriggerPayload):
    return run(p.event_id, settings)
