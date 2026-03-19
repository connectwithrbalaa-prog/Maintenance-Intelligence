from fastapi.testclient import TestClient
from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import metrics as metrics_module
from maintenance_intelligence.runner.edge_command_buffer import EdgeCommandBuffer
from maintenance_intelligence.runner.edge_agent import EdgeEventBuffer

def test_metrics_endpoint(tmp_path, monkeypatch):
    buffer_path = tmp_path / "edge-metrics.sqlite3"
    command_buffer_path = tmp_path / "edge-command-metrics.sqlite3"
    buffer = EdgeEventBuffer(str(buffer_path), max_events=10)
    command_buffer = EdgeCommandBuffer(str(command_buffer_path))
    buffer.buffer_event(
        {
            "event_id": "EV-OFFLINE",
            "occurred_at": "2026-03-15T10:00:00Z",
            "org_id": "demo-org",
            "asset_id": "PUMP-101",
            "kind": "anomaly",
            "severity": "high",
            "summary": "Offline buffered event",
            "details": {"source": "edge"},
            "lineage": {"channel": "kafka"},
        },
        error="central store unavailable",
    )
    command_buffer.enqueue_command(
        "REC-1",
        {
            "proposal_id": "REC-1",
            "recommendation_id": "REC-1",
            "recommendation": {"id": "REC-1", "asset_id": "PUMP-101"},
        },
        error="cmms offline",
    )
    monkeypatch.setenv("MI_EDGE_MODE_ENABLED", "true")
    monkeypatch.setenv("MI_EDGE_BUFFER_PATH", str(buffer_path))
    monkeypatch.setenv("MI_EDGE_COMMAND_BUFFER_PATH", str(command_buffer_path))
    monkeypatch.setattr(
        metrics_module.cmms_handoff_snapshot_collector,
        "load_snapshot",
        lambda: {
            "up": 1,
            "summary": {
                "success_total": 2,
                "pending_total": 1,
                "failure_total": 1,
                "retryable_failure_total": 1,
                "terminal_failure_total": 0,
                "admin_retry_required_total": 2,
                "limit_reached_total": 1,
                "approval_to_handoff_seconds_avg": 450,
            },
            "by_backend": {
                "maximo": {
                    "pending_total": 1,
                    "failure_total": 0,
                    "retryable_failure_total": 0,
                    "terminal_failure_total": 0,
                    "admin_retry_required_total": 1,
                    "limit_reached_total": 0,
                },
            },
        },
    )
    c = TestClient(app)
    r = c.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "rca_runs_total" in body
    assert "events_ingested_total" in body
    assert "cmms_handoff_backlog_total" in body
    assert "cmms_handoff_retryable_failure_total 1.0" in body
    assert "cmms_handoff_terminal_failure_total 0.0" in body
    assert 'cmms_handoff_backend_backlog_total{backend="maximo"}' in body
    assert 'cmms_handoff_backend_retryable_failure_total{backend="maximo"} 0.0' in body
    assert "edge_buffer_depth 1.0" in body
    assert "edge_buffered_events_total 1.0" in body
    assert 'edge_connectivity_state{status="offline"} 1.0' in body
    assert "edge_command_queue_depth 1.0" in body
    assert "edge_command_queued_total 1.0" in body