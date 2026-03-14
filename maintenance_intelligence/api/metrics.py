from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
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
rca_latency_seconds = Histogram(
    "rca_latency_seconds",
    "RCA model latency (seconds) by model and prompt",
    ["service", "model", "prompt_id"],
    registry=REGISTRY,
    buckets=(0.1, 0.3, 1, 3, 10, 30, 60, 120),
)
rca_cost_usd_total = Counter(
    "rca_cost_usd_total",
    "Estimated RCA spend in USD by model and prompt",
    ["model", "prompt_id"],
    registry=REGISTRY,
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
rca_runs_by_prompt_total = Counter(
    "rca_runs_by_prompt_total",
    "Total RCA runs by route and prompt",
    ["service", "route", "prompt_id", "variant"],
    registry=REGISTRY,
)
prompt_feedback_total = Counter(
    "prompt_feedback_total",
    "Total prompt-linked feedback items",
    ["route", "prompt_id", "action"],
    registry=REGISTRY,
)

# Kafka lag gauge (optional; set by health checks if desired)
kafka_consume_lag = Gauge(
    "kafka_consume_lag", "Kafka consumer group lag (total)", ["group"], registry=REGISTRY
)
rca_budget_cap_usd = Gauge(
    "rca_budget_cap_usd",
    "Configured RCA spend cap in USD by budget window",
    ["window"],
    registry=REGISTRY,
)


def publish_budget_caps(budget_caps: dict[str, float]):
    for window, amount in (budget_caps or {}).items():
        try:
            rca_budget_cap_usd.labels(window=window).set(max(0.0, float(amount)))
        except (TypeError, ValueError):
            continue


@router.get("/metrics")
def metrics():
    try:
        from maintenance_intelligence.runner.config import Settings

        publish_budget_caps(Settings().rca_budget_caps_usd)
    except Exception:
        pass
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
