from fastapi.testclient import TestClient
from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import metrics as metrics_module

def test_metrics_endpoint(monkeypatch):
    monkeypatch.setattr(
        metrics_module.cmms_handoff_snapshot_collector,
        "load_snapshot",
        lambda: {
            "up": 1,
            "summary": {
                "success_total": 2,
                "pending_total": 1,
                "failure_total": 1,
                "admin_retry_required_total": 2,
                "limit_reached_total": 1,
                "approval_to_handoff_seconds_avg": 450,
            },
            "by_backend": {
                "maximo": {
                    "pending_total": 1,
                    "failure_total": 0,
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
    assert 'cmms_handoff_backend_backlog_total{backend="maximo"}' in body