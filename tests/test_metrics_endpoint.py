from fastapi.testclient import TestClient
from maintenance_intelligence.api.main import app

def test_metrics_endpoint():
    c = TestClient(app)
    r = c.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "rca_runs_total" in body
    assert "events_ingested_total" in body