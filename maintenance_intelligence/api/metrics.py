from fastapi import APIRouter, Response
from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from maintenance_intelligence.api.outcomes import (
    _empty_cmms_summary,
    _finalize_cmms_bucket,
    _update_cmms_bucket,
    with_pg,
    _workorder_backend,
)
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.context.assembler import get_context_cache_snapshot
from maintenance_intelligence.runner.edge_agent import EdgeEventBuffer
from maintenance_intelligence.runner.edge_command_buffer import EdgeCommandBuffer

router = APIRouter()

# Global registry and metrics (process-wide)
REGISTRY = CollectorRegistry(auto_describe=True)

# Core counters/histograms
rca_runs_total = Counter("rca_runs_total", "Total RCA runs", ["service"], registry=REGISTRY)
rca_failures_total = Counter("rca_failures_total", "Total RCA run failures", ["service"], registry=REGISTRY)
rca_duration_seconds = Histogram("rca_duration_seconds", "RCA run duration (seconds)", ["service"], registry=REGISTRY, buckets=(0.1,0.3,1,3,10,30,60,120))

events_ingested_total = Counter("events_ingested_total", "Total events ingested", ["service"], registry=REGISTRY)
recommendations_created_total = Counter("recommendations_created_total", "Total recommendations created", ["service"], registry=REGISTRY)
wo_drafts_total = Counter("wo_drafts_total", "Total WO drafts created", ["service"], registry=REGISTRY)

# Kafka lag gauge (optional; set by health checks if desired)
kafka_consume_lag = Gauge("kafka_consume_lag", "Kafka consumer group lag (total)", ["group"], registry=REGISTRY)


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
                cur.execute(
                    """
                    SELECT
                        p.status,
                        p.work_order_id,
                        p.metadata,
                        w.handoff_completed_at,
                        w.metadata
                    FROM pm_proposals p
                    LEFT JOIN workorders w ON w.wo_id = p.work_order_id
                    WHERE p.created_at > NOW() - INTERVAL '30 days'
                    """
                )
                for row in cur.fetchall() or []:
                    if not row:
                        continue
                    status = row[0]
                    work_order_id = row[1]
                    proposal_metadata = row[2] if isinstance(row[2], dict) else {}
                    handoff_completed_at = row[3] if len(row) > 3 else None
                    workorder_metadata = row[4] if len(row) > 4 and isinstance(row[4], dict) else {}

                    _update_cmms_bucket(summary, status, work_order_id, proposal_metadata, handoff_completed_at, max_attempts)
                    backend_key = _workorder_backend(workorder_metadata)
                    _update_cmms_bucket(by_backend.setdefault(backend_key, _empty_cmms_summary()), status, work_order_id, proposal_metadata, handoff_completed_at, max_attempts)
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

        metrics_up = GaugeMetricFamily("cmms_handoff_metrics_up", "Whether CMMS handoff metrics scraped successfully")
        metrics_up.add_metric([], float(snapshot.get("up") or 0))
        yield metrics_up

        summary_fields = {
            "cmms_handoff_success_total": ("CMMS handoff successes observed in the last 30 days", float(summary.get("success_total") or 0)),
            "cmms_handoff_pending_total": ("CMMS handoff proposals still pending in the last 30 days", float(summary.get("pending_total") or 0)),
            "cmms_handoff_failure_total": ("CMMS handoff proposals in failure state in the last 30 days", float(summary.get("failure_total") or 0)),
            "cmms_handoff_admin_retry_required_total": ("CMMS handoff proposals requiring admin retry review in the last 30 days", float(summary.get("admin_retry_required_total") or 0)),
            "cmms_handoff_limit_reached_total": ("CMMS handoff proposals that hit the retry ceiling in the last 30 days", float(summary.get("limit_reached_total") or 0)),
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
            "cmms_handoff_backend_pending_total": ("Per-backend CMMS pending handoff proposals in the last 30 days", "pending_total"),
            "cmms_handoff_backend_failure_total": ("Per-backend CMMS handoff failures in the last 30 days", "failure_total"),
            "cmms_handoff_backend_admin_retry_required_total": ("Per-backend CMMS proposals requiring admin retry review in the last 30 days", "admin_retry_required_total"),
            "cmms_handoff_backend_limit_reached_total": ("Per-backend CMMS proposals that hit the retry ceiling in the last 30 days", "limit_reached_total"),
        }
        backend_backlog_metric = GaugeMetricFamily(
            "cmms_handoff_backend_backlog_total",
            "Per-backend CMMS handoff backlog in pending or failure state in the last 30 days",
            labels=["backend"],
        )
        for backend, backend_summary in sorted(by_backend.items()):
            backend_backlog_metric.add_metric(
                [backend],
                float(backend_summary.get("pending_total") or 0) + float(backend_summary.get("failure_total") or 0),
            )
        for metric_name, (description, summary_key) in backend_metric_specs.items():
            metric = GaugeMetricFamily(metric_name, description, labels=["backend"])
            for backend, backend_summary in sorted(by_backend.items()):
                metric.add_metric([backend], float(backend_summary.get(summary_key) or 0))
            yield metric
        yield backend_backlog_metric


class EdgeBufferSnapshotCollector:
    _CONNECTIVITY_STATES = ("disabled", "unknown", "online", "degraded", "offline")

    def load_snapshot(self):
        settings = Settings()
        if not settings.edge_mode_enabled:
            return {
                "up": 1,
                "edge_mode_enabled": 0,
                "snapshot": {
                    "connectivity_status": "disabled",
                    "buffered_event_count": 0,
                    "total_buffered_events": 0,
                    "total_replayed_events": 0,
                    "total_replay_failures": 0,
                },
            }
        try:
            buffer = EdgeEventBuffer(settings.edge_buffer_path, max_events=settings.edge_buffer_max_events)
            return {
                "up": 1,
                "edge_mode_enabled": 1,
                "snapshot": buffer.snapshot(),
            }
        except Exception:
            return {
                "up": 0,
                "edge_mode_enabled": 1,
                "snapshot": {
                    "connectivity_status": "unknown",
                    "buffered_event_count": 0,
                    "total_buffered_events": 0,
                    "total_replayed_events": 0,
                    "total_replay_failures": 0,
                },
            }

    def collect(self):
        payload = self.load_snapshot()
        snapshot = payload.get("snapshot") or {}
        connectivity_status = str(snapshot.get("connectivity_status") or "unknown")

        metrics_up = GaugeMetricFamily("edge_buffer_metrics_up", "Whether edge buffer metrics scraped successfully")
        metrics_up.add_metric([], float(payload.get("up") or 0))
        yield metrics_up

        mode_enabled = GaugeMetricFamily("edge_mode_enabled", "Whether edge mode is enabled for this process")
        mode_enabled.add_metric([], float(payload.get("edge_mode_enabled") or 0))
        yield mode_enabled

        buffer_depth = GaugeMetricFamily("edge_buffer_depth", "Current number of buffered edge events awaiting replay")
        buffer_depth.add_metric([], float(snapshot.get("buffered_event_count") or 0))
        yield buffer_depth

        buffered_events_total = CounterMetricFamily("edge_buffered_events", "Total edge events buffered locally while offline")
        buffered_events_total.add_metric([], float(snapshot.get("total_buffered_events") or 0))
        yield buffered_events_total

        replayed_events_total = CounterMetricFamily("edge_replayed_events", "Total buffered edge events successfully replayed to central storage")
        replayed_events_total.add_metric([], float(snapshot.get("total_replayed_events") or 0))
        yield replayed_events_total

        replay_failures_total = CounterMetricFamily("edge_replay_failures", "Total failed edge replay attempts")
        replay_failures_total.add_metric([], float(snapshot.get("total_replay_failures") or 0))
        yield replay_failures_total

        connectivity_metric = GaugeMetricFamily("edge_connectivity_state", "Current edge connectivity state by status label", labels=["status"])
        for state in self._CONNECTIVITY_STATES:
            connectivity_metric.add_metric([state], 1.0 if connectivity_status == state else 0.0)
        yield connectivity_metric


class EdgeCommandBufferSnapshotCollector:
    def load_snapshot(self):
        settings = Settings()
        if not settings.edge_mode_enabled:
            return {
                "up": 1,
                "edge_mode_enabled": 0,
                "snapshot": {
                    "queued_command_count": 0,
                    "total_queued_commands": 0,
                    "total_replayed_commands": 0,
                    "total_replay_failures": 0,
                },
            }
        try:
            buffer = EdgeCommandBuffer(settings.edge_command_buffer_path)
            return {
                "up": 1,
                "edge_mode_enabled": 1,
                "snapshot": buffer.snapshot(),
            }
        except Exception:
            return {
                "up": 0,
                "edge_mode_enabled": 1,
                "snapshot": {
                    "queued_command_count": 0,
                    "total_queued_commands": 0,
                    "total_replayed_commands": 0,
                    "total_replay_failures": 0,
                },
            }

    def collect(self):
        payload = self.load_snapshot()
        snapshot = payload.get("snapshot") or {}

        metrics_up = GaugeMetricFamily("edge_command_queue_metrics_up", "Whether edge command queue metrics scraped successfully")
        metrics_up.add_metric([], float(payload.get("up") or 0))
        yield metrics_up

        queue_depth = GaugeMetricFamily("edge_command_queue_depth", "Current number of queued CMMS handoffs awaiting replay")
        queue_depth.add_metric([], float(snapshot.get("queued_command_count") or 0))
        yield queue_depth

        queued_total = CounterMetricFamily("edge_command_queued_total", "Total CMMS handoffs queued locally while offline")
        queued_total.add_metric([], float(snapshot.get("total_queued_commands") or 0))
        yield queued_total

        replayed_total = CounterMetricFamily("edge_command_replayed_total", "Total queued CMMS handoffs drained from the local queue")
        replayed_total.add_metric([], float(snapshot.get("total_replayed_commands") or 0))
        yield replayed_total

        replay_failures_total = CounterMetricFamily("edge_command_replay_failures_total", "Total failed CMMS handoff replay attempts from the local queue")
        replay_failures_total.add_metric([], float(snapshot.get("total_replay_failures") or 0))
        yield replay_failures_total


class ContextCacheSnapshotCollector:
    def load_snapshot(self):
        settings = Settings()
        snapshot = get_context_cache_snapshot()
        return {
            "up": 1,
            "context_cache_enabled": 1 if settings.context_cache_enabled else 0,
            "ttl_s": int(settings.context_cache_ttl_s),
            "max_entries": int(settings.context_cache_max_entries),
            "snapshot": snapshot,
        }

    def collect(self):
        payload = self.load_snapshot()
        snapshot = payload.get("snapshot") or {}

        metrics_up = GaugeMetricFamily("context_cache_metrics_up", "Whether context cache metrics scraped successfully")
        metrics_up.add_metric([], float(payload.get("up") or 0))
        yield metrics_up

        enabled = GaugeMetricFamily("context_cache_enabled", "Whether the in-process context cache is enabled")
        enabled.add_metric([], float(payload.get("context_cache_enabled") or 0))
        yield enabled

        ttl_metric = GaugeMetricFamily("context_cache_ttl_seconds", "Configured TTL for context cache entries in seconds")
        ttl_metric.add_metric([], float(payload.get("ttl_s") or 0))
        yield ttl_metric

        max_entries_metric = GaugeMetricFamily("context_cache_max_entries", "Configured maximum number of context cache entries")
        max_entries_metric.add_metric([], float(payload.get("max_entries") or 0))
        yield max_entries_metric

        entries_metric = GaugeMetricFamily("context_cache_entries", "Current number of cached context entries")
        entries_metric.add_metric([], float(snapshot.get("entries") or 0))
        yield entries_metric

        counter_specs = {
            "context_cache_hits_total": ("Total fresh context cache hits", "hits"),
            "context_cache_misses_total": ("Total context cache misses", "misses"),
            "context_cache_refreshes_total": ("Total stale context cache refreshes", "refreshes"),
            "context_cache_evictions_total": ("Total context cache evictions", "evictions"),
            "context_cache_prefetches_total": ("Total context cache prefetch operations", "prefetches"),
        }
        for metric_name, (description, key) in counter_specs.items():
            metric = CounterMetricFamily(metric_name, description)
            metric.add_metric([], float(snapshot.get(key) or 0))
            yield metric


cmms_handoff_snapshot_collector = CMMSSnapshotCollector()
REGISTRY.register(cmms_handoff_snapshot_collector)
edge_buffer_snapshot_collector = EdgeBufferSnapshotCollector()
REGISTRY.register(edge_buffer_snapshot_collector)
edge_command_buffer_snapshot_collector = EdgeCommandBufferSnapshotCollector()
REGISTRY.register(edge_command_buffer_snapshot_collector)
context_cache_snapshot_collector = ContextCacheSnapshotCollector()
REGISTRY.register(context_cache_snapshot_collector)

@router.get("/metrics")
def metrics():
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)