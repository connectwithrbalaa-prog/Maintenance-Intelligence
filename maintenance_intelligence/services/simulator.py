import datetime as dt
import json
import signal
import sys
import time
import uuid

import backoff
from kafka import KafkaProducer
from kafka.errors import KafkaError
from loguru import logger

from maintenance_intelligence.multitenancy import scoped_topic
from maintenance_intelligence.runner.config import Settings


@backoff.on_exception(backoff.expo, KafkaError, max_tries=5, max_time=60)
def create_kafka_producer(kafka_bootstrap: str):
    """Create Kafka producer with retry logic."""
    return KafkaProducer(
        bootstrap_servers=kafka_bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",  # Wait for all replicas
        retries=3,
        retry_backoff_ms=1000,
    )


@backoff.on_exception(backoff.expo, KafkaError, max_tries=3, max_time=30)
def send_event(producer, topic, event, settings: Settings):
    """Send event with retry logic."""
    future = producer.send(scoped_topic(topic, settings, event.get("org_id")), event)
    producer.flush()  # Wait for send to complete
    return future


def simulator(kafka_bootstrap: str):
    logger.info({"event": "simulator.start", "kafka_bootstrap": kafka_bootstrap})
    settings = Settings()

    # Graceful shutdown handling
    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        logger.info({"event": "simulator.shutdown_requested", "signal": signum})
        shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    prod = None
    try:
        prod = create_kafka_producer(kafka_bootstrap)
        asset_ids = ["PUMP-101", "PUMP-102", "COMP-201"]

        while not shutdown_requested:
            for a in asset_ids:
                if shutdown_requested:
                    break

                evt = {
                    "event_type": "event.raised",
                    "event_id": str(uuid.uuid4()),
                    "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
                    "org_id": "demo-org",
                    "asset_id": a,
                    "kind": "alarm",
                    "severity": "high",
                    "summary": f"High vibration on {a}",
                    "details": {"rms": 9.2, "threshold": 7.5},
                    "lineage": {"source": "simulator"},
                }

                try:
                    send_event(prod, "canonical.event.raised", evt, settings)
                    logger.debug(
                        {"event": "simulator.sent", "asset_id": a, "event_id": evt["event_id"]}
                    )
                except Exception as e:
                    logger.error({"event": "simulator.send_failed", "asset_id": a, "error": str(e)})
                    # Continue with next asset rather than crashing

            if not shutdown_requested:
                time.sleep(2)

    except Exception as e:
        logger.error({"event": "simulator.error", "error": str(e)})
        sys.exit(1)
    finally:
        if prod:
            logger.info({"event": "simulator.shutting_down"})
            prod.close(timeout=10)  # Wait up to 10 seconds for pending sends
            logger.info({"event": "simulator.stopped"})

    logger.info({"event": "simulator.exit"})
