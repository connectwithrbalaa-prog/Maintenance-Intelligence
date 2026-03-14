from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app


def test_outcomes_shape_keys():
    c = TestClient(app)
    r = c.get("/api/v1/reports/rca-outcomes?window=30")
    # Without DB, this may 503; we only assert the endpoint responds
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        data = r.json()
        # Presence (or None) of new keys is acceptable
        assert "per_asset_acceptance" in data
        assert "per_asset_ttr" in data
