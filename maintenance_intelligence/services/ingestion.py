import json
import signal
import sys

import backoff
import psycopg2
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from loguru import logger

from maintenance_intelligence.api.metrics import events_ingested_total
from maintenance_intelligence.multitenancy import consumer_topics, event_in_scope
from maintenance_intelligence.runner.config import Settings


@backoff.on_exception(backoff.expo, psycopg2.Error, max_tries=5, max_time=60)
def create_db_connection(dsn: str):
    """Create database connection with retry logic."""
    return psycopg2.connect(dsn)


@backoff.on_exception(backoff.expo, KafkaError, max_tries=5, max_time=60)
def create_kafka_consumer(kafka_bootstrap: str, settings: Settings):
    """Create Kafka consumer with retry logic."""
    return KafkaConsumer(
        *consumer_topics(
            ["canonical.asset.upserted", "canonical.event.raised"],
            settings,
            org_id=settings.default_org,
        ),
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        group_id="agent-ingestion",
        auto_offset_reset="earliest",
        enable_auto_commit=True,  # Auto-commit offsets
        auto_commit_interval_ms=5000,  # Commit every 5 seconds
    )


@backoff.on_exception(backoff.expo, (psycopg2.Error, Exception), max_tries=3, max_time=30)
def store_event(conn, evt):
    """Store event in database with retry logic."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events(event_id, occurred_at, org_id, asset_id, kind, severity, summary, details, lineage) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) "
                "ON CONFLICT (event_id) DO NOTHING",
                (
                    evt.get("event_id"),
                    evt.get("occurred_at"),
                    evt.get("org_id"),
                    evt.get("asset_id"),
                    evt.get("kind"),
                    evt.get("severity"),
                    evt.get("summary"),
                    json.dumps(evt.get("details")),
                    json.dumps(evt.get("lineage")),
                ),
            )


def ingestion(kafka_bootstrap: str, pg_dsn: str):
    logger.info({"event": "ingestion.start", "kafka_bootstrap": kafka_bootstrap})
    settings = Settings()

    # Graceful shutdown handling
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        logger.info({"event": "ingestion.shutdown_requested", "signal": signum})
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    conn = None
    cons = None

    try:
        conn = create_db_connection(pg_dsn)
        cons = create_kafka_consumer(kafka_bootstrap, settings)

        for msg in cons:
            if shutdown_requested:
                break

            evt = msg.value
            if not event_in_scope(evt.get("org_id"), settings, org_id=settings.default_org):
                continue
            if evt.get("event_type") == "event.raised":
                try:
                    store_event(conn, evt)
                    logger.info({"event": "ingestion.stored", "id": evt.get("event_id")})
                    events_ingested_total.labels(service="ingestion").inc()
                except Exception as e:
                    logger.error(
                        {
                            "event": "ingestion.store_failed",
                            "id": evt.get("event_id"),
                            "error": str(e),
                        }
                    )
                    # Continue processing other messages

    except Exception as e:
        logger.error({"event": "ingestion.error", "error": str(e)})
        sys.exit(1)
    finally:
        logger.info({"event": "ingestion.shutting_down"})
        if cons:
            cons.close()
        if conn:
            conn.close()
        logger.info({"event": "ingestion.stopped"})

    logger.info({"event": "ingestion.exit"})
