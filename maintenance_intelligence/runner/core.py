from loguru import logger

from .config import Settings
from .logging import run_id, setup_logger, timed


@timed
def run(event_id: str, settings: Settings, org_id: str | None = None):
    setup_logger(settings.log_level)
    rid = run_id()
    logger.bind(run_id=rid).info({"event": "runner.start", "event_id": event_id, "org_id": org_id})
    rec_id = f"rec-{rid[:8]}"
    logger.info(
        {"event": "recommendation.stub", "id": rec_id, "note": "Kafka pipeline handles real flow"}
    )
    return {"run_id": rid, "status": "ok", "recommendation_id": rec_id, "org_id": org_id}
