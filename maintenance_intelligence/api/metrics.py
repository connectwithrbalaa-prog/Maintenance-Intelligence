from fastapi import APIRouter, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from prometheus_client.core import GaugeMetricFamily

from maintenance_intelligence.api.outcomes import (
    _empty_cmms_summary,
    _finalize_cmms_bucket,
    _update_cmms_bucket,
    with_pg,
    _workorder_backend,
)
from maintenance_intelligence.runner.config import Settings

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


class CMMSSnapshotCollector:
    def load_snapshot(self):
        summary = _empty_cmms_summary()
        by_backend = {}
        settings = Settings()
        conn = None
        try:
            conn = with_pg(settings.pg_dsn)
            max_attempts = max(1, int(settings.pm_handoff_max_attempts_per_proposal))
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        p.status,
                        p.work_order_id,
                        p.metadata,
                        w.handoff_completed_at,
                        w.metadata
                    FROM pm_proposals p
                    LEFT JOIN workorders w ON w.wo_id = p.work_order_id
                    WHERE p.created_at > NOW() - INTERVAL '30 days'
                    """)
                for row in cur.fetchall() or []:
                    if not row:
                        continue
                    status = row[0]
                    work_order_id = row[1]
                    proposal_metadata = row[2] if isinstance(row[2], dict) else {}
                    handoff_completed_at = row[3] if len(row) > 3 else None
                    workorder_metadata = row[4] if len(row) > 4 and isinstance(row[4], dict) else {}

                    _update_cmms_bucket(
                        summary,
                        status,
                        work_order_id,
                        proposal_metadata,
                        handoff_completed_at,
                        max_attempts,
                    )
                    backend_key = _workorder_backend(workorder_metadata)
                    _update_cmms_bucket(
                        by_backend.setdefault(backend_key, _empty_cmms_summary()),
                        status,
                        work_order_id,
                        proposal_metadata,
                        handoff_completed_at,
                        max_attempts,
                    )
        except Exception:
            return {"up": 0, "summary": _empty_cmms_summary(), "by_backend": {}}
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        _finalize_cmms_bucket(summary)
        for bucket in by_backend.values():
            _finalize_cmms_bucket(bucket)
        return {"up": 1, "summary": summary, "by_backend": by_backend}

    def collect(self):
        snapshot = self.load_snapshot()
        summary = snapshot.get("summary") or {}
        by_backend = snapshot.get("by_backend") or {}

        metrics_up = GaugeMetricFamily(
            "cmms_handoff_metrics_up", "Whether CMMS handoff metrics scraped successfully"
        )
        metrics_up.add_metric([], float(snapshot.get("up") or 0))
        yield metrics_up

        summary_fields = {
            "cmms_handoff_success_total": (
                "CMMS handoff successes observed in the last 30 days",
                float(summary.get("success_total") or 0),
            ),
            "cmms_handoff_pending_total": (
                "CMMS handoff proposals still pending in the last 30 days",
                float(summary.get("pending_total") or 0),
            ),
            "cmms_handoff_failure_total": (
                "CMMS handoff proposals in failure state in the last 30 days",
                float(summary.get("failure_total") or 0),
            ),
            "cmms_handoff_admin_retry_required_total": (
                "CMMS handoff proposals requiring admin retry review in the last 30 days",
                float(summary.get("admin_retry_required_total") or 0),
            ),
            "cmms_handoff_limit_reached_total": (
                "CMMS handoff proposals that hit the retry ceiling in the last 30 days",
                float(summary.get("limit_reached_total") or 0),
            ),
            "cmms_handoff_backlog_total": (
                "CMMS handoff proposals still open in pending or failure state in the last 30 days",
                float(summary.get("pending_total") or 0) + float(summary.get("failure_total") or 0),
            ),
        }
        lead_time_avg = summary.get("approval_to_handoff_seconds_avg")
        if lead_time_avg is not None:
            summary_fields["cmms_handoff_approval_to_handoff_seconds_avg"] = (
                "Average approval-to-handoff lead time for successful CMMS handoffs in the last 30 days",
                float(lead_time_avg),
            )

        for metric_name, (description, value) in summary_fields.items():
            metric = GaugeMetricFamily(metric_name, description)
            metric.add_metric([], value)
            yield metric

        backend_metric_specs = {
            "cmms_handoff_backend_pending_total": (
                "Per-backend CMMS pending handoff proposals in the last 30 days",
                "pending_total",
            ),
            "cmms_handoff_backend_failure_total": (
                "Per-backend CMMS handoff failures in the last 30 days",
                "failure_total",
            ),
            "cmms_handoff_backend_admin_retry_required_total": (
                "Per-backend CMMS proposals requiring admin retry review in the last 30 days",
                "admin_retry_required_total",
            ),
            "cmms_handoff_backend_limit_reached_total": (
                "Per-backend CMMS proposals that hit the retry ceiling in the last 30 days",
                "limit_reached_total",
            ),
        }
        backend_backlog_metric = GaugeMetricFamily(
            "cmms_handoff_backend_backlog_total",
            "Per-backend CMMS handoff backlog in pending or failure state in the last 30 days",
            labels=["backend"],
        )
        for backend, backend_summary in sorted(by_backend.items()):
            backend_backlog_metric.add_metric(
                [backend],
                float(backend_summary.get("pending_total") or 0)
                + float(backend_summary.get("failure_total") or 0),
            )
        for metric_name, (description, summary_key) in backend_metric_specs.items():
            metric = GaugeMetricFamily(metric_name, description, labels=["backend"])
            for backend, backend_summary in sorted(by_backend.items()):
                metric.add_metric([backend], float(backend_summary.get(summary_key) or 0))
            yield metric
        yield backend_backlog_metric


cmms_handoff_snapshot_collector = CMMSSnapshotCollector()
REGISTRY.register(cmms_handoff_snapshot_collector)


@router.get("/metrics")
def metrics():
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
