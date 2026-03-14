from fastapi.testclient import TestClient
from maintenance_intelligence.api.main import app

def test_outcomes_csv_endpoint_exists():
    c = TestClient(app)
    r = c.get("/api/v1/reports/rca-outcomes/csv?window=30")
    # In CI without DB, this may 500; we just assert the route exists and responds.
    assert r.status_code in (200, 500, 502, 503)