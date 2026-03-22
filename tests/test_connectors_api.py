"""Tests for CMMS connector management API."""

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.ingestion.pipeline import _create_adapter

client = TestClient(app)
HEADERS = {"X-User-Id": "test.admin", "X-User-Role": "admin", "X-Org-Id": "test-org"}


def test_connector_status():
    resp = client.get("/api/v1/connectors/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "sap_pm" in data
    assert "maximo" in data
    assert "tenant_id" in data


def test_connector_status_requires_auth():
    resp = client.get("/api/v1/connectors/status")
    assert resp.status_code == 403


def test_test_sap_not_configured():
    resp = client.post("/api/v1/connectors/test/sap", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "not_configured"


def test_test_maximo_not_configured():
    resp = client.post("/api/v1/connectors/test/maximo", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "not_configured"


def test_test_unknown_source():
    resp = client.post("/api/v1/connectors/test/oracle", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_sync_sap_no_endpoint():
    resp = client.post("/api/v1/connectors/sync/sap", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["equipment_synced"] == 0


def test_sync_maximo_no_endpoint():
    resp = client.post("/api/v1/connectors/sync/maximo", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["equipment_synced"] == 0


def test_sync_unknown_source():
    resp = client.post("/api/v1/connectors/sync/oracle", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_sync_requires_auth():
    resp = client.post("/api/v1/connectors/sync/sap")
    assert resp.status_code == 403


def test_create_adapter_sap():
    from maintenance_intelligence.runner.config import Settings
    settings = Settings()
    adapter = _create_adapter("SAP", settings)
    assert adapter.source_system == "SAP"
    assert adapter.adapter_name == "sap_pm"


def test_create_adapter_maximo():
    from maintenance_intelligence.runner.config import Settings
    settings = Settings()
    adapter = _create_adapter("MAXIMO", settings)
    assert adapter.source_system == "MAXIMO"
