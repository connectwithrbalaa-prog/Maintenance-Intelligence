from fastapi import APIRouter, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

router = APIRouter()

# Global registry and metrics (process-wide)
REGISTRY = CollectorRegistry(auto_describe=True)

# Core counters/histograms
rca_runs_total = Counter("rca_runs_total", "Total RCA runs", ["service"], registry=REGISTRY)
rca_failures_total = Counter(
    "rca_failures_total", "Total RCA run failures", ["service"], registry=REGISTRY
)
rca_duration_seconds = Histogram(
    "rca_duration_seconds",
    "RCA run duration (seconds)",
    ["service"],
    registry=REGISTRY,
    buckets=(0.1, 0.3, 1, 3, 10, 30, 60, 120),
)

events_ingested_total = Counter(
    "events_ingested_total", "Total events ingested", ["service"], registry=REGISTRY
)
recommendations_created_total = Counter(
    "recommendations_created_total", "Total recommendations created", ["service"], registry=REGISTRY
)
wo_drafts_total = Counter(
    "wo_drafts_total", "Total WO drafts created", ["service"], registry=REGISTRY
)

# Kafka lag gauge (optional; set by health checks if desired)
kafka_consume_lag = Gauge(
    "kafka_consume_lag", "Kafka consumer group lag (total)", ["group"], registry=REGISTRY
)


@router.get("/metrics")
def metrics():
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
