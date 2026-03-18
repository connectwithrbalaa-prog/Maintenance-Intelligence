import json
import signal
import sys
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import psycopg2
from loguru import logger
import backoff
from maintenance_intelligence.api.metrics import events_ingested_total
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.edge_agent import EdgeEventBuffer
from maintenance_intelligence.services.connectivity import open_central_connection, safe_close_connection


@backoff.on_exception(backoff.expo, psycopg2.Error, max_tries=5, max_time=60)
def create_db_connection(dsn: str):
    """Create database connection with retry logic."""
    return psycopg2.connect(dsn)


@backoff.on_exception(backoff.expo, KafkaError, max_tries=5, max_time=60)
def create_kafka_consumer(kafka_bootstrap: str):
    """Create Kafka consumer with retry logic."""
    return KafkaConsumer(
        "canonical.asset.upserted",
        "canonical.event.raised",
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

def _replay_buffered_events(conn, edge_buffer: EdgeEventBuffer, batch_size: int) -> dict:
    replayed_total = 0
    while edge_buffer.buffered_event_count() > 0:
        outcome = edge_buffer.replay(conn, store_event, batch_size=batch_size)
        replayed_total += int(outcome.get("replayed") or 0)
        if outcome.get("error"):
            return {"replayed": replayed_total, "error": outcome.get("error")}
        if not outcome.get("replayed"):
            break
    return {"replayed": replayed_total, "error": None}


def _connect_edge_central(pg_dsn: str, settings: Settings, edge_buffer: EdgeEventBuffer):
    try:
        conn = open_central_connection(pg_dsn, timeout_s=settings.edge_connectivity_timeout_s)
        edge_buffer.mark_connectivity("online", last_error=None)
        return conn
    except Exception as exc:
        edge_buffer.mark_connectivity("offline", last_error=str(exc))
        return None


def ingestion(kafka_bootstrap: str, pg_dsn: str):
    logger.info({"event": "ingestion.start", "kafka_bootstrap": kafka_bootstrap})
    settings = Settings()
    edge_buffer = EdgeEventBuffer(settings.edge_buffer_path, max_events=settings.edge_buffer_max_events) if settings.edge_mode_enabled else None

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
        cons = create_kafka_consumer(kafka_bootstrap)
        if settings.edge_mode_enabled:
            edge_buffer.mark_connectivity("unknown", last_error=None)
            conn = _connect_edge_central(pg_dsn, settings, edge_buffer)
        else:
            conn = create_db_connection(pg_dsn)
        next_connectivity_probe_at = 0.0

        for msg in cons:
            if shutdown_requested:
                break

            evt = msg.value
            if evt.get("event_type") == "event.raised":
                if not settings.edge_mode_enabled:
                    try:
                        store_event(conn, evt)
                        logger.info({"event": "ingestion.stored", "id": evt.get("event_id")})
                        events_ingested_total.labels(service="ingestion").inc()
                    except Exception as e:
                        logger.error({"event": "ingestion.store_failed", "id": evt.get("event_id"), "error": str(e)})
                    continue

                now = time.time()
                if conn is None and now >= next_connectivity_probe_at:
                    conn = _connect_edge_central(pg_dsn, settings, edge_buffer)
                    if conn is None:
                        next_connectivity_probe_at = now + settings.edge_connectivity_check_interval_s

                if conn is not None and edge_buffer.buffered_event_count() > 0:
                    replayed = _replay_buffered_events(conn, edge_buffer, settings.edge_replay_batch_size)
                    if replayed.get("replayed"):
                        logger.info({"event": "ingestion.edge_replayed", "count": replayed.get("replayed")})
                    if replayed.get("error"):
                        logger.error({"event": "ingestion.edge_replay_failed", "error": replayed.get("error")})
                        safe_close_connection(conn)
                        conn = None
                        next_connectivity_probe_at = now + settings.edge_connectivity_check_interval_s

                if conn is None:
                    queued = edge_buffer.buffer_event(evt, error="Central store unavailable")
                    logger.warning({"event": "ingestion.buffered", "id": evt.get("event_id"), "buffer_id": queued})
                    continue

                try:
                    store_event(conn, evt)
                    edge_buffer.mark_central_write_succeeded()
                    logger.info({"event": "ingestion.stored", "id": evt.get("event_id")})
                    events_ingested_total.labels(service="ingestion").inc()
                except Exception as e:
                    logger.error({"event": "ingestion.store_failed", "id": evt.get("event_id"), "error": str(e)})
                    safe_close_connection(conn)
                    conn = None
                    edge_buffer.buffer_event(evt, error=str(e))
                    edge_buffer.mark_connectivity("degraded", last_error=str(e))
                    next_connectivity_probe_at = now + settings.edge_connectivity_check_interval_s

    except Exception as e:
        logger.error({"event": "ingestion.error", "error": str(e)})
        sys.exit(1)
    finally:
        logger.info({"event": "ingestion.shutting_down"})
        if cons:
            cons.close()
        safe_close_connection(conn)
        logger.info({"event": "ingestion.stopped"})

    logger.info({"event": "ingestion.exit"})
