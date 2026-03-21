import json
import datetime as dt
import signal
import sys
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.logging import get_logger
import psycopg2
import psycopg2.extras
from collections import defaultdict
import statistics
import backoff

logger = get_logger(__name__)


@backoff.on_exception(backoff.expo, KafkaError, max_tries=5, max_time=60)
def create_kafka_consumer(kafka_bootstrap: str):
    """Create Kafka consumer with retry logic."""
    return KafkaConsumer(
        "canonical.event.raised",
        bootstrap_servers=kafka_bootstrap,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        group_id="signals-processor",
        enable_auto_commit=True,
        auto_commit_interval_ms=5000,
    )


@backoff.on_exception(backoff.expo, KafkaError, max_tries=5, max_time=60)
def create_kafka_producer(kafka_bootstrap: str):
    """Create Kafka producer with retry logic."""
    return KafkaProducer(
        bootstrap_servers=kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=3,
        retry_backoff_ms=1000,
    )


@backoff.on_exception(backoff.expo, psycopg2.Error, max_tries=5, max_time=60)
def create_db_connection(db_url: str):
    """Create database connection with retry logic."""
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    return conn


@backoff.on_exception(backoff.expo, KafkaError, max_tries=3, max_time=30)
def send_anomaly_event(producer, anomaly_event):
    """Send anomaly event with retry logic."""
    producer.send("canonical.signal.anomaly.detected", anomaly_event)
    producer.flush()


def signals_processor(kafka_bootstrap: str = None, db_url: str = None):
    """Process events to extract signals, compute rollups, and detect anomalies."""
    logger.info({"event": "signals_processor.start"})

    # Graceful shutdown handling
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        logger.info({"event": "signals_processor.shutdown_requested", "signal": signum})
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    settings = Settings()
    kafka_bootstrap = kafka_bootstrap or settings.kafka_bootstrap
    db_url = db_url or settings.database_url

    cons = None
    prod = None
    conn = None

    try:
        cons = create_kafka_consumer(kafka_bootstrap)
        prod = create_kafka_producer(kafka_bootstrap)
        conn = create_db_connection(db_url)

        # Track recent values for anomaly detection (simple z-score)
        recent_values = defaultdict(list)  # (asset_id, signal_type) -> [values]

        for msg in cons:
            if shutdown_requested:
                break

            evt = msg.value
            if evt.get("kind") not in ("alarm", "anomaly", "measurement"):
                continue

            try:
                asset_id = evt.get("asset_id")
                details = evt.get("details", {})

                # Extract signals from details (assume vibration, temperature, etc.)
                signals = []
                if "rms" in details:
                    signals.append(("vibration", details["rms"], "mm/s"))
                if "temperature" in details:
                    signals.append(("temperature", details["temperature"], "C"))
                # Add more signal types as needed

                for signal_type, value, unit in signals:
                    signal_id = f"{asset_id}-{signal_type}-{evt['event_id']}"

                    # Insert signal
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO signals (signal_id, asset_id, signal_type, timestamp, value, unit, metadata)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (signal_id) DO NOTHING
                        """,
                            (
                                signal_id,
                                asset_id,
                                signal_type,
                                evt["occurred_at"],
                                value,
                                unit,
                                {"event_id": evt["event_id"], "source": "event"},
                            ),
                        )

                    # Update recent values for anomaly detection
                    key = (asset_id, signal_type)
                    recent_values[key].append(value)
                    if len(recent_values[key]) > 100:  # Keep last 100 values
                        recent_values[key].pop(0)

                    # Compute rollups every 5 minutes (in real system, use cron or scheduler)
                    _compute_rollups(conn, asset_id, signal_type)

                    # Detect anomalies
                    anomaly_flags = _detect_anomalies(
                        recent_values[key], value, details.get("threshold")
                    )
                    if anomaly_flags:
                        # Send anomaly event
                        anomaly_evt = {
                            "event_type": "signal.anomaly.detected",
                            "event_id": f"anomaly-{signal_id}",
                            "occurred_at": dt.datetime.now(dt.timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z"),
                            "org_id": evt["org_id"],
                            "asset_id": asset_id,
                            "kind": "anomaly",
                            "severity": "medium",
                            "summary": f"Anomaly detected in {signal_type} for {asset_id}",
                            "details": {
                                "signal_type": signal_type,
                                "value": value,
                                "anomaly_flags": anomaly_flags,
                                "threshold": details.get("threshold"),
                            },
                            "lineage": {
                                "source": "signals-processor",
                                "parent_event_id": evt["event_id"],
                            },
                        }
                        send_anomaly_event(prod, anomaly_evt)

                logger.info(
                    {
                        "event": "signals.processed",
                        "asset_id": asset_id,
                        "signals_count": len(signals),
                    }
                )

            except Exception as e:
                logger.error(
                    {
                        "event": "signals_processor.processing_error",
                        "event_id": evt.get("event_id"),
                        "error": str(e),
                    }
                )
                # Continue processing other events

    except Exception as e:
        logger.error({"event": "signals_processor.error", "error": str(e)})
        sys.exit(1)
    finally:
        logger.info({"event": "signals_processor.shutting_down"})
        if cons:
            cons.close()
        if prod:
            prod.close(timeout=10)
        if conn:
            conn.close()
        logger.info({"event": "signals_processor.stopped"})

    logger.info({"event": "signals_processor.exit"})


def _compute_rollups(conn, asset_id: str, signal_type: str):
    """Compute 1h, 6h, 24h rollups for the last period."""
    now = dt.datetime.now(dt.timezone.utc)
    periods = [
        ("1h", dt.timedelta(hours=1)),
        ("6h", dt.timedelta(hours=6)),
        ("24h", dt.timedelta(hours=24)),
    ]

    for period_name, delta in periods:
        start_time = now - delta

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT value FROM signals
                WHERE asset_id = %s AND signal_type = %s AND timestamp >= %s
                ORDER BY timestamp
            """,
                (asset_id, signal_type, start_time),
            )

            values = [row["value"] for row in cur.fetchall()]
            if not values:
                continue

            mean_val = statistics.mean(values)
            min_val = min(values)
            max_val = max(values)
            count = len(values)

            # Simple anomaly flags based on thresholds
            anomaly_flags = {}
            if signal_type == "vibration" and max_val > 10:  # Example threshold
                anomaly_flags["high_vibration"] = True
            if signal_type == "temperature" and max_val > 80:  # Example threshold
                anomaly_flags["high_temperature"] = True

            rollup_id = f"{asset_id}-{signal_type}-{period_name}-{now.isoformat()}"

            cur.execute(
                """
                INSERT INTO signal_rollups (rollup_id, asset_id, signal_type, period, start_time, end_time,
                                           mean_value, min_value, max_value, count, anomaly_flags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (rollup_id) DO UPDATE SET
                    mean_value = EXCLUDED.mean_value,
                    min_value = EXCLUDED.min_value,
                    max_value = EXCLUDED.max_value,
                    count = EXCLUDED.count,
                    anomaly_flags = EXCLUDED.anomaly_flags
            """,
                (
                    rollup_id,
                    asset_id,
                    signal_type,
                    period_name,
                    start_time,
                    now,
                    mean_val,
                    min_val,
                    max_val,
                    count,
                    json.dumps(anomaly_flags),
                ),
            )


def _detect_anomalies(recent_values: list, current_value: float, threshold: float = None) -> dict:
    """Simple anomaly detection using z-score and threshold."""
    anomalies = {}

    # Threshold-based
    if threshold and current_value > threshold * 1.5:
        anomalies["threshold_exceeded"] = True

    # Z-score based
    if len(recent_values) >= 10:
        mean = statistics.mean(recent_values)
        stdev = statistics.stdev(recent_values) if len(recent_values) > 1 else 0
        if stdev > 0:
            z_score = abs(current_value - mean) / stdev
            if z_score > 3:
                anomalies["z_score_spike"] = True

    return anomalies
