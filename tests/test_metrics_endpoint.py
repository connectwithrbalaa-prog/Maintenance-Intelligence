from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app


def test_metrics_endpoint(monkeypatch):
    monkeypatch.setenv("MI_RCA_BUDGET_CAPS_USD", '{"daily":12.5,"weekly":55.0}')
    c = TestClient(app)
    r = c.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "rca_runs_total" in body
    assert "rca_cost_usd_total" in body
    assert "rca_latency_seconds" in body
    assert 'rca_budget_cap_usd{window="daily"} 12.5' in body
    assert "events_ingested_total" in body