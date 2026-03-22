"""Tests for ISO 14224 hierarchy, taxonomy, and failure event API endpoints."""

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app

client = TestClient(app)

HEADERS = {
    "X-User-Id": "test.engineer",
    "X-User-Role": "admin",
    "X-Org-Id": "test-org",
}


# ── Taxonomy endpoints ──


def test_taxonomy_failure_modes():
    resp = client.get("/api/v1/taxonomy/failure-modes", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 20
    codes = [r["code"] for r in data]
    assert "VIB" in codes
    assert "FTS" in codes
    assert "ELP" in codes


def test_taxonomy_failure_mechanisms():
    resp = client.get("/api/v1/taxonomy/failure-mechanisms", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 14
    codes = [r["code"] for r in data]
    assert "WEA" in codes
    assert "COR" in codes


def test_taxonomy_failure_causes():
    resp = client.get("/api/v1/taxonomy/failure-causes", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 7
    codes = [r["code"] for r in data]
    assert "OPC" in codes
    assert "MNT" in codes


def test_taxonomy_failure_causes_filter_by_category():
    resp = client.get("/api/v1/taxonomy/failure-causes?category=OPERATION", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["category"] == "OPERATION" for r in data)


def test_taxonomy_maintenance_actions():
    resp = client.get("/api/v1/taxonomy/maintenance-actions", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    codes = [r["code"] for r in data]
    assert "REP" in codes
    assert "OVH" in codes


def test_taxonomy_maintenance_actions_filter():
    resp = client.get("/api/v1/taxonomy/maintenance-actions?maintenance_category=PREVENTIVE", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["maintenance_category"] == "PREVENTIVE" for r in data)


def test_taxonomy_detection_methods():
    resp = client.get("/api/v1/taxonomy/detection-methods", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    codes = [r["code"] for r in data]
    assert "MON" in codes


def test_taxonomy_equipment_families():
    resp = client.get("/api/v1/taxonomy/equipment-families", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "EF-ROT" in data
    assert "EF-STAT" in data
    assert "EF-ELEC" in data
    assert "EF-INST" in data
    assert "EF-SAFE" in data
    assert "EF-PACK" in data
    rot = data["EF-ROT"]
    assert "CENTRIFUGAL_PUMP" in rot["equipment_classes"]
    assert "GAS_TURBINE" in rot["equipment_classes"]


def test_taxonomy_equipment_family_detail():
    resp = client.get("/api/v1/taxonomy/equipment-families/EF-ROT", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "EF-ROT"
    assert "BEARING_RADIAL" in data["component_types"]


def test_taxonomy_equipment_family_not_found():
    resp = client.get("/api/v1/taxonomy/equipment-families/EF-NONEXISTENT", headers=HEADERS)
    assert resp.status_code == 404


def test_taxonomy_process_templates():
    resp = client.get("/api/v1/taxonomy/process-templates", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "PF-WELL" in data
    assert "PF-SURF" in data
    assert "SEPARATION" in data["PF-SURF"]["system_types"]


# ── Taxonomy auth ──


def test_taxonomy_requires_auth():
    resp = client.get("/api/v1/taxonomy/failure-modes")
    assert resp.status_code == 403


# ── Hierarchy endpoints ──


def test_hierarchy_sites():
    resp = client.get("/api/v1/hierarchy/sites", headers=HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_hierarchy_equipment_empty():
    resp = client.get("/api/v1/hierarchy/equipment", headers=HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_hierarchy_equipment_not_found():
    resp = client.get("/api/v1/hierarchy/equipment/NONEXISTENT", headers=HEADERS)
    assert resp.status_code == 404


def test_hierarchy_requires_auth():
    resp = client.get("/api/v1/hierarchy/sites")
    assert resp.status_code == 403


# ── Failure events endpoints ──


def test_failure_events_list_empty():
    resp = client.get("/api/v1/failure-events", headers=HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_failure_events_not_found():
    resp = client.get("/api/v1/failure-events/NONEXISTENT", headers=HEADERS)
    assert resp.status_code == 404


def test_failure_events_requires_auth():
    resp = client.get("/api/v1/failure-events")
    assert resp.status_code == 403


def test_failure_events_create_requires_auth():
    resp = client.post("/api/v1/failure-events", json={"source_system": "MANUAL"})
    assert resp.status_code == 403
