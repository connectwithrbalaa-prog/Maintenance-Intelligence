from fastapi.testclient import TestClient
from maintenance_intelligence.api.main import app

def test_health_basic():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
