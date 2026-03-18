import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for name in list(sys.modules):
    if name == "maintenance_intelligence" or name.startswith("maintenance_intelligence."):
        del sys.modules[name]

from maintenance_intelligence.cmms.adapter import (
    CMMSPayloadError,
    CMMSUnavailableError,
    UnsupportedBackendError,
    create_cmms_adapter,
    discover_cmms_backends,
    lifecycle_phase_for_status,
    normalize_work_order_lifecycle,
    parse_json_response_body,
    post_json_request,
    supported_cmms_backends,
)
from maintenance_intelligence.cmms.maximo import MaximoCMMSAdapter
from maintenance_intelligence.cmms.mock import MockCMMSAdapter
from maintenance_intelligence.cmms.sap_pm import SAPPMCMMSAdapter
from maintenance_intelligence.cmms.servicenow import ServiceNowCMMSAdapter
from maintenance_intelligence.cmms.translators import translate_connector_response
from maintenance_intelligence.runner.config import Settings


def test_factory_selects_mock_backend(monkeypatch):
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "mock")

    adapter = create_cmms_adapter(Settings())

    assert adapter.backend_name == MockCMMSAdapter.backend_name


def test_factory_selects_maximo_backend(monkeypatch):
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "maximo")

    adapter = create_cmms_adapter(Settings())

    assert adapter.backend_name == MaximoCMMSAdapter.backend_name


def test_factory_selects_sap_pm_backend_with_alias(monkeypatch):
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "sap-pm")

    adapter = create_cmms_adapter(Settings())

    assert adapter.backend_name == SAPPMCMMSAdapter.backend_name


def test_factory_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "oracle")

    with pytest.raises(UnsupportedBackendError, match="Supported backends: maximo, mock, sap_pm, servicenow"):
        create_cmms_adapter(Settings())


def test_supported_backends_exposes_registry():
    assert supported_cmms_backends() == ["maximo", "mock", "sap_pm", "servicenow"]


def test_discover_cmms_backends_reports_required_config_fields():
    metadata = discover_cmms_backends(
        Settings(
            pm_connector_backend="sap_pm",
            sap_pm_base_url="https://sap.example.test",
        )
    )

    assert metadata["current_backend"] == "sap_pm"
    sap_backend = next(item for item in metadata["supported_backends"] if item["backend"] == "sap_pm")
    assert sap_backend["configured"] is True
    assert any(field["env_var"] == "MI_SAP_PM_BASE_URL" and field["required"] for field in sap_backend["config_fields"])
    assert {entry["phase"]: entry["statuses"] for entry in sap_backend["lifecycle_statuses"]}["completed"] == ["CLSD", "TECO"]
    maximo_backend = next(item for item in metadata["supported_backends"] if item["backend"] == "maximo")
    assert maximo_backend["configured"] is False


def test_factory_selects_servicenow_backend(monkeypatch):
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "servicenow")

    adapter = create_cmms_adapter(Settings())

    assert adapter.backend_name == ServiceNowCMMSAdapter.backend_name


def test_shared_http_helpers_post_and_parse_json():
    class FakeResponse:
        content = b'{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class FakeClient:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    client = FakeClient()
    response = post_json_request(
        client,
        endpoint="https://example.test/workorders",
        payload={"id": "REC-1"},
        headers={"Accept": "application/json"},
        unavailable_detail="connector down",
    )
    body = parse_json_response_body(
        response,
        invalid_json_detail="bad json",
        malformed_payload_detail="bad payload",
    )

    assert client.calls[0]["url"] == "https://example.test/workorders"
    assert body == {"ok": True}


def test_translate_connector_response_maps_backend_specific_fields():
    translated = translate_connector_response(
        {
            "OrderNumber": "50000123",
            "OrderStatus": "TECO",
            "CreatedAt": "2026-03-15T10:30:00Z",
            "TechnicalCompletionDate": "2026-03-15T11:00:00Z",
            "Message": "Created",
        },
        backend_name="sap_pm",
        recommendation={"id": "REC-9"},
        wo_id_fields=("OrderNumber", "MaintenanceOrder"),
        status_fields=("OrderStatus", "Status"),
        message_fields=("Message",),
        workorder_created_fields=("CreatedAt",),
        handoff_completed_fields=("SystemStatusDate", "CreatedAt"),
        workorder_completed_fields=("CompletedAt", "TechnicalCompletionDate"),
        default_status="REL",
    )

    assert translated["wo_id"] == "50000123"
    assert translated["status"] == "TECO"
    assert translated["message"] == "Created"
    assert translated["handoff_completed_at"] == "2026-03-15T10:30:00Z"
    assert translated["workorder_completed_at"] == "2026-03-15T11:00:00Z"


def test_normalize_work_order_lifecycle_marks_incomplete_handoff_as_pending():
    lifecycle = normalize_work_order_lifecycle(
        {
            "status": "queued",
            "workorder_created_at": "2026-03-15T10:30:00Z",
            "handoff_complete": False,
        },
        handoff_complete=False,
    )

    assert lifecycle["handoff_complete"] is False
    assert lifecycle["handoff_completed_at"] is None
    assert lifecycle["phase"] == "pending"
    assert lifecycle["terminal"] is False


def test_lifecycle_phase_for_status_uses_connector_mapping():
    assert lifecycle_phase_for_status("teco", {"TECO": "completed"}) == "completed"
    assert lifecycle_phase_for_status("wappr", {"WAPPR": "handoff-complete"}) == "handoff-complete"


def test_normalize_work_order_result_preserves_connector_phase_hints_on_second_pass():
    first_pass = MockCMMSAdapter(Settings()).create_work_order({"id": "REC-1", "asset_id": "PUMP-101", "title": "Inspect seal"})

    second_pass = normalize_work_order_lifecycle(first_pass)

    assert second_pass["phase"] == "handoff-complete"


def test_mock_adapter_returns_normalized_work_order():
    adapter = MockCMMSAdapter(Settings())

    result = adapter.create_work_order({"id": "REC-12345678", "asset_id": "PUMP-101", "title": "Inspect seal"})

    assert result["wo_id"] == "WO-REC-1234"
    assert result["status"] == "DRAFT"
    assert result["backend"] == "mock"
    assert result["workorder_created_at"] == result["created_at"]
    assert result["handoff_completed_at"] == result["created_at"]
    assert result["workorder_completed_at"] is None
    assert result["lifecycle_phase"] == "handoff-complete"
    assert result["lifecycle"]["terminal"] is False


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
        Settings(maximo_base_url="https://maximo.example.test", maximo_site="PLANT1", maximo_api_key="secret"),
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
    assert result["lifecycle_phase"] == "completed"
    assert result["terminal_state"] is True


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


def test_sap_pm_adapter_requires_base_url():
    adapter = SAPPMCMMSAdapter(Settings())

    with pytest.raises(CMMSUnavailableError, match="MI_SAP_PM_BASE_URL"):
        adapter.create_work_order({"id": "REC-1", "asset_id": "PUMP-101", "title": "Inspect seal"})


def test_sap_pm_adapter_maps_and_parses_odata_response():
    class FakeResponse:
        content = b'{"d":{"OrderNumber":"50000123","OrderStatus":"TECO","CreatedAt":"2026-03-15T10:30:00Z","TechnicalCompletionDate":"2026-03-15T11:00:00Z","Message":"Created"}}'

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "d": {
                    "OrderNumber": "50000123",
                    "OrderStatus": "TECO",
                    "CreatedAt": "2026-03-15T10:30:00Z",
                    "TechnicalCompletionDate": "2026-03-15T11:00:00Z",
                    "Message": "Created",
                }
            }

    class FakeClient:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    client = FakeClient()
    adapter = SAPPMCMMSAdapter(
        Settings(
            sap_pm_base_url="https://sap.example.test",
            sap_pm_plant="1710",
            sap_pm_order_type="PM02",
        ),
        client=client,
    )

    result = adapter.create_work_order(
        {
            "id": "REC-9",
            "asset_id": "PUMP-101",
            "title": "Inspect seal",
            "rationale": "Elevated vibration",
            "priority": "HIGH",
        }
    )

    assert client.calls[0]["url"] == "https://sap.example.test/sap/opu/odata/sap/ZMI_WORKORDER_SRV/WorkOrders"
    assert client.calls[0]["json"]["Equipment"] == "PUMP-101"
    assert client.calls[0]["json"]["Plant"] == "1710"
    assert client.calls[0]["json"]["OrderType"] == "PM02"
    assert result["wo_id"] == "50000123"
    assert result["backend"] == "sap_pm"
    assert result["workorder_created_at"] == "2026-03-15T10:30:00Z"
    assert result["handoff_completed_at"] == "2026-03-15T10:30:00Z"
    assert result["workorder_completed_at"] == "2026-03-15T11:00:00Z"
    assert result["lifecycle_phase"] == "completed"
    assert result["lifecycle"]["terminal"] is True


def test_servicenow_adapter_requires_base_url():
    adapter = ServiceNowCMMSAdapter(Settings())

    with pytest.raises(CMMSUnavailableError, match="MI_SERVICENOW_BASE_URL"):
        adapter.create_work_order({"id": "REC-1", "asset_id": "PUMP-101", "title": "Inspect seal"})


def test_servicenow_adapter_maps_and_parses_response():
    class FakeResponse:
        content = b'{"result":{"number":"WO0001234","state_display":"Open","sys_created_on":"2026-03-15T10:30:00Z","message":"Created"}}'

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": {
                    "number": "WO0001234",
                    "state_display": "Open",
                    "sys_created_on": "2026-03-15T10:30:00Z",
                    "message": "Created",
                }
            }

    class FakeClient:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    client = FakeClient()
    adapter = ServiceNowCMMSAdapter(
        Settings(
            servicenow_base_url="https://instance.service-now.test",
            servicenow_table="wm_order",
        ),
        client=client,
    )

    result = adapter.create_work_order(
        {
            "id": "REC-11",
            "asset_id": "PUMP-101",
            "title": "Inspect seal",
            "rationale": "Elevated vibration",
            "priority": "HIGH",
        }
    )

    assert client.calls[0]["url"] == "https://instance.service-now.test/api/now/table/wm_order"
    assert client.calls[0]["json"]["cmdb_ci"] == "PUMP-101"
    assert result["wo_id"] == "WO0001234"
    assert result["backend"] == "servicenow"
    assert result["lifecycle_phase"] == "active"
    assert result["terminal_state"] is False