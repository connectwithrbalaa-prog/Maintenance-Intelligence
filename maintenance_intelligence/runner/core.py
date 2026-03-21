from .config import Settings
from .logging import setup_logger, run_id, timed
from loguru import logger


@timed
def run(event_id: str, settings: Settings):
    setup_logger(settings.log_level)
    rid = run_id()
    logger.bind(run_id=rid).info({"event": "runner.start", "event_id": event_id})
    rec_id = f"rec-{rid[:8]}"
    logger.info(
        {"event": "recommendation.stub", "id": rec_id, "note": "Kafka pipeline handles real flow"}
    )
    return {"run_id": rid, "status": "ok", "recommendation_id": rec_id}
