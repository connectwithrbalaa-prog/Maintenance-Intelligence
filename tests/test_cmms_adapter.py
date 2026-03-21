import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for name in list(sys.modules):
    if name == "maintenance_intelligence" or name.startswith("maintenance_intelligence."):
        del sys.modules[name]

from maintenance_intelligence.cmms.adapter import (  # noqa: E402
    CMMSPayloadError,
    UnsupportedBackendError,
    create_cmms_adapter,
)
from maintenance_intelligence.cmms.maximo import MaximoCMMSAdapter  # noqa: E402
from maintenance_intelligence.cmms.mock import MockCMMSAdapter  # noqa: E402
from maintenance_intelligence.runner.config import Settings  # noqa: E402


def test_factory_selects_mock_backend(monkeypatch):
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "mock")

    adapter = create_cmms_adapter(Settings())

    assert adapter.backend_name == MockCMMSAdapter.backend_name


def test_factory_selects_maximo_backend(monkeypatch):
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "maximo")

    adapter = create_cmms_adapter(Settings())

    assert adapter.backend_name == MaximoCMMSAdapter.backend_name


def test_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "sap")

    with pytest.raises(UnsupportedBackendError):
        create_cmms_adapter(Settings())


def test_mock_adapter_returns_normalized_work_order():
    adapter = MockCMMSAdapter(Settings())

    result = adapter.create_work_order(
        {"id": "REC-12345678", "asset_id": "PUMP-101", "title": "Inspect seal"}
    )

    assert result["wo_id"] == "WO-REC-1234"
    assert result["status"] == "DRAFT"
    assert result["backend"] == "mock"
    assert result["workorder_created_at"] == result["created_at"]
    assert result["handoff_completed_at"] == result["created_at"]
    assert result["workorder_completed_at"] is None


def test_maximo_adapter_maps_and_parses_response(monkeypatch):
    class FakeResponse:
        content = b'{"wonum":"MX-1001","status":"COMP","statusdate":"2026-03-15T10:30:00Z","actfinish":"2026-03-15T11:00:00Z"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "wonum": "MX-1001",
                "status": "COMP",
                "statusdate": "2026-03-15T10:30:00Z",
                "actfinish": "2026-03-15T11:00:00Z",
            }

    class FakeClient:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    client = FakeClient()
    adapter = MaximoCMMSAdapter(
        Settings(
            maximo_base_url="https://maximo.example.test",
            maximo_site="PLANT1",
            maximo_api_key="secret",
        ),
        client=client,
    )

    result = adapter.create_work_order(
        {
            "id": "REC-1",
            "asset_id": "PUMP-101",
            "title": "Inspect seal",
            "rationale": "Elevated vibration",
            "priority": "HIGH",
        }
    )

    assert client.calls[0]["url"] == "https://maximo.example.test/oslc/os/mxwo"
    assert client.calls[0]["json"]["assetnum"] == "PUMP-101"
    assert client.calls[0]["json"]["siteid"] == "PLANT1"
    assert client.calls[0]["headers"]["x-api-key"] == "secret"
    assert result["wo_id"] == "MX-1001"
    assert result["backend"] == "maximo"
    assert result["handoff_completed_at"] == "2026-03-15T10:30:00Z"
    assert result["workorder_completed_at"] == "2026-03-15T11:00:00Z"


def test_maximo_adapter_rejects_invalid_json(monkeypatch):
    class FakeResponse:
        content = b"not-json"

        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("bad json")

    class FakeClient:
        def post(self, url, json, headers):
            return FakeResponse()

    adapter = MaximoCMMSAdapter(
        Settings(maximo_base_url="https://maximo.example.test"),
        client=FakeClient(),
    )

    with pytest.raises(CMMSPayloadError):
        adapter.create_work_order({"id": "REC-1", "asset_id": "PUMP-101", "title": "Inspect seal"})
