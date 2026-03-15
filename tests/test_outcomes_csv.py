from fastapi.testclient import TestClient
from maintenance_intelligence.api.main import app

def test_outcomes_csv_endpoint_exists():
    c = TestClient(app)
    r = c.get("/api/v1/reports/rca-outcomes/csv?window=30")
    # In CI without DB, this should degrade to an upstream-availability response, not a missing route.
    assert r.status_code in (200, 503)