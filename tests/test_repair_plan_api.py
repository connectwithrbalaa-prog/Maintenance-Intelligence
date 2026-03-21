from datetime import datetime, timezone

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import repair_plan as repair_plan_mod


class FakeService:
    def __init__(self):
        self.created = {
            "plan_id": "RP-123",
            "run_id": "RUN-123",
            "recommendation_id": "REC-123",
            "org_id": "demo-org",
            "asset_id": "PUMP-101",
            "summary": "Replace bearing",
            "rationale": "Repeated vibration alarms",
            "confidence": 0.91,
            "status": "pending",
            "created_at": datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc).isoformat(),
            "updated_at": datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc).isoformat(),
        }
        self.part = {
            "part_id": "PART-123",
            "plan_id": "RP-123",
            "name": "Bearing kit",
            "description": "OEM bearing replacement",
            "quantity": 1,
            "unit": "ea",
            "metadata": {"sku": "BRG-9"},
            "created_at": datetime(2026, 3, 17, 9, 5, tzinfo=timezone.utc).isoformat(),
        }


def test_repair_plan_endpoints_round_trip(monkeypatch):
    fake = FakeService()
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(
        repair_plan_mod, "create_repair_plan", lambda dsn, **kwargs: {**fake.created, **kwargs}
    )
    monkeypatch.setattr(
        repair_plan_mod,
        "get_repair_plan",
        lambda dsn, plan_id: fake.created if plan_id == "RP-123" else None,
    )
    monkeypatch.setattr(repair_plan_mod, "list_repair_plans", lambda dsn, limit=100: [fake.created])
    monkeypatch.setattr(
        repair_plan_mod, "delete_repair_plan", lambda dsn, plan_id: plan_id == "RP-123"
    )
    monkeypatch.setattr(
        repair_plan_mod,
        "add_part_to_plan",
        lambda dsn, plan_id, **kwargs: {**fake.part, **kwargs, "plan_id": plan_id},
    )
    monkeypatch.setattr(
        repair_plan_mod,
        "list_parts_for_plan",
        lambda dsn, plan_id: [fake.part] if plan_id == "RP-123" else [],
    )

    client = TestClient(app)

    create_response = client.post(
        "/api/v1/repair-plans/",
        json={
            "run_id": "RUN-123",
            "recommendation_id": "REC-123",
            "org_id": "demo-org",
            "asset_id": "PUMP-101",
            "summary": "Replace bearing",
            "rationale": "Repeated vibration alarms",
            "confidence": 0.91,
        },
        headers={"x-user-id": "planner-1", "x-user-role": "planner"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["plan_id"] == "RP-123"

    read_headers = {"x-user-id": "viewer-1", "x-user-role": "viewer"}

    list_response = client.get("/api/v1/repair-plans/?limit=10", headers=read_headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["recommendation_id"] == "REC-123"

    get_response = client.get("/api/v1/repair-plans/RP-123", headers=read_headers)
    assert get_response.status_code == 200
    assert get_response.json()["parts"][0]["part_id"] == "PART-123"

    add_part_response = client.post(
        "/api/v1/repair-plans/RP-123/parts",
        json={
            "name": "Bearing kit",
            "description": "OEM bearing replacement",
            "quantity": 1,
            "unit": "ea",
            "metadata": {"sku": "BRG-9"},
        },
        headers={"x-user-id": "maint-1", "x-user-role": "maintainer"},
    )
    assert add_part_response.status_code == 200
    assert add_part_response.json()["metadata"] == {"sku": "BRG-9"}

    parts_response = client.get("/api/v1/repair-plans/RP-123/parts", headers=read_headers)
    assert parts_response.status_code == 200
    assert parts_response.json()[0]["name"] == "Bearing kit"

    delete_response = client.delete(
        "/api/v1/repair-plans/RP-123", headers={"x-user-id": "admin-1", "x-user-role": "admin"}
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}


def test_repair_plan_endpoints_handle_missing_plan(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(repair_plan_mod, "get_repair_plan", lambda dsn, plan_id: None)

    client = TestClient(app)
    read_headers = {"x-user-id": "viewer-1", "x-user-role": "viewer"}

    get_response = client.get("/api/v1/repair-plans/RP-missing", headers=read_headers)
    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Repair plan not found"

    parts_response = client.get("/api/v1/repair-plans/RP-missing/parts", headers=read_headers)
    assert parts_response.status_code == 404
    assert parts_response.json()["detail"] == "Repair plan not found"


def test_repair_plan_openapi_schema_is_exposed():
    client = TestClient(app)

    response = client.get("/openapi.json")
    assert response.status_code == 200

    payload = response.json()
    assert "/api/v1/repair-plans/" in payload["paths"]
    assert payload["paths"]["/api/v1/repair-plans/"]["post"]["summary"] == "Create a repair plan"
    assert (
        payload["paths"]["/api/v1/repair-plans/{plan_id}/parts"]["post"]["summary"]
        == "Add a repair part"
    )


def test_repair_plan_write_endpoints_require_allowed_role(monkeypatch):
    fake = FakeService()
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(
        repair_plan_mod, "create_repair_plan", lambda dsn, **kwargs: {**fake.created, **kwargs}
    )
    monkeypatch.setattr(
        repair_plan_mod,
        "get_repair_plan",
        lambda dsn, plan_id: fake.created if plan_id == "RP-123" else None,
    )

    client = TestClient(app)

    create_response = client.post(
        "/api/v1/repair-plans/",
        json={"run_id": "RUN-123", "recommendation_id": "REC-123"},
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )
    assert create_response.status_code == 403
    assert (
        create_response.json()["detail"]
        == "Repair plan writes require planner, maintainer, or admin role"
    )

    add_part_response = client.post(
        "/api/v1/repair-plans/RP-123/parts",
        json={"name": "Bearing kit", "quantity": 1},
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )
    assert add_part_response.status_code == 403
    assert (
        add_part_response.json()["detail"]
        == "Repair plan writes require planner, maintainer, or admin role"
    )

    delete_response = client.delete(
        "/api/v1/repair-plans/RP-123",
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )
    assert delete_response.status_code == 403
    assert (
        delete_response.json()["detail"]
        == "Repair plan writes require planner, maintainer, or admin role"
    )


def test_repair_plan_read_endpoints_require_authenticated_identity(monkeypatch):
    fake = FakeService()
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    monkeypatch.setattr(
        repair_plan_mod,
        "get_repair_plan",
        lambda dsn, plan_id: fake.created if plan_id == "RP-123" else None,
    )
    monkeypatch.setattr(repair_plan_mod, "list_repair_plans", lambda dsn, limit=100: [fake.created])
    monkeypatch.setattr(
        repair_plan_mod,
        "list_parts_for_plan",
        lambda dsn, plan_id: [fake.part] if plan_id == "RP-123" else [],
    )

    client = TestClient(app)

    list_response = client.get("/api/v1/repair-plans/?limit=10")
    get_response = client.get("/api/v1/repair-plans/RP-123")
    parts_response = client.get("/api/v1/repair-plans/RP-123/parts")

    assert list_response.status_code == 403
    assert list_response.json()["detail"] == "Repair plan reads require an authenticated identity"
    assert get_response.status_code == 403
    assert get_response.json()["detail"] == "Repair plan reads require an authenticated identity"
    assert parts_response.status_code == 403
    assert parts_response.json()["detail"] == "Repair plan reads require an authenticated identity"
