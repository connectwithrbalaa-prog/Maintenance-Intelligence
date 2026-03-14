from fastapi import APIRouter, Query
from maintenance_intelligence.runner.config import Settings
import socket, psycopg2
from kafka import KafkaAdminClient

router = APIRouter()

@router.get("/healthz")
def healthz(deep: bool = Query(False, description="Enable deep checks (Kafka/PG)")):
    info = {"status": "ok", "host": socket.gethostname()}
    if not deep:
        return info

    settings = Settings()
    # PG check
    try:
        conn = psycopg2.connect(settings.pg_dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            info["pg"] = "ok"
        finally:
            conn.close()
    except Exception as e:
        info["pg"] = f"error: {e}"
        info["status"] = "degraded"

    # Kafka check
    try:
        admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap, client_id="mi-health")
        topics = admin.list_topics()
        info["kafka"] = "ok" if topics is not None else "unknown"
    except Exception as e:
        info["kafka"] = f"error: {e}"
        info["status"] = "degraded"

    return info
