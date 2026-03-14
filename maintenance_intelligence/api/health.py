from fastapi import APIRouter
from maintenance_intelligence.runner.config import Settings
import socket

router = APIRouter()

@router.get("/healthz")
def healthz():
    # Basic process-level health; deeper checks can be added (Kafka/PG pings)
    return {"status": "ok", "host": socket.gethostname()}
