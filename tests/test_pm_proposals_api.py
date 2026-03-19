import json
import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for name in list(sys.modules):
    if name == "maintenance_intelligence" or name.startswith("maintenance_intelligence."):
        del sys.modules[name]


def _load_local_module(module_name, relative_path):
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_load_local_module("maintenance_intelligence.runner.config", Path("maintenance_intelligence/runner/config.py"))
_load_local_module("maintenance_intelligence.runner.edge_command_buffer", Path("maintenance_intelligence/runner/edge_command_buffer.py"))
_load_local_module("maintenance_intelligence.api.metrics", Path("maintenance_intelligence/api/metrics.py"))
identity_mod = _load_local_module("maintenance_intelligence.api.middleware.identity", Path("maintenance_intelligence/api/middleware/identity.py"))
_load_local_module("maintenance_intelligence.cmms.adapter", Path("maintenance_intelligence/cmms/adapter.py"))
_load_local_module("maintenance_intelligence.cmms.mock", Path("maintenance_intelligence/cmms/mock.py"))
_load_local_module("maintenance_intelligence.cmms.maximo", Path("maintenance_intelligence/cmms/maximo.py"))
sap_pm_mod = _load_local_module("maintenance_intelligence.cmms.sap_pm", Path("maintenance_intelligence/cmms/sap_pm.py"))
servicenow_mod = _load_local_module("maintenance_intelligence.cmms.servicenow", Path("maintenance_intelligence/cmms/servicenow.py"))
_load_local_module("maintenance_intelligence.services.wo_bridge", Path("maintenance_intelligence/services/wo_bridge.py"))
pm_mod = _load_local_module("maintenance_intelligence.api.pm_advisor", Path("maintenance_intelligence/api/pm_advisor.py"))
app = FastAPI()
identity_mod.install_identity_middleware(app)
app.include_router(pm_mod.router)

READ_HEADERS = {"x-user-id": "viewer-1", "x-user-role": "viewer"}


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.executed = connection.executed

    def execute(self, query, params):
        self.connection.execute(query, params)

    def fetchall(self):
        return self.connection.fetchall()

    def fetchone(self):
        return self.connection.fetchone()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.closed = False
        self.proposals = {}
        self.workorders = {}
        self._last_rows = []

    def cursor(self):
        return FakeCursor(self)

    def execute(self, query, params):
        self.executed.append((query, params))
        normalized = " ".join(query.split())
        if normalized.startswith("INSERT INTO pm_proposals"):
            record = {
                "proposal_id": params[0],
                "run_id": params[1],
                "recommendation_id": params[2],
                "event_id": params[3],
                "asset_id": params[4],
                "title": params[5],
                "rationale": params[6],
                "confidence": params[7],
                "status": params[8],
                "source_file": params[9],
                "proposed_by": params[10],
                "approved_by": params[11],
                "work_order_id": params[12],
                "metadata": json.loads(params[13]),
            }
            existing = self.proposals.get(record["proposal_id"])
            if existing:
                record["status"] = existing["status"]
                record["approved_by"] = existing["approved_by"]
                record["work_order_id"] = existing["work_order_id"]
                if existing["proposed_by"]:
                    record["proposed_by"] = existing["proposed_by"]
                record["metadata"] = {**existing.get("metadata", {}), **record.get("metadata", {})}
            self.proposals[record["proposal_id"]] = record
            self._last_rows = [self._row(record)]
        elif normalized.startswith("SELECT proposal_id"):
            rows = [self._row(record) for record in self.proposals.values()]
            rows.sort(key=lambda row: (row[0]), reverse=True)
            self._last_rows = rows
        elif normalized.startswith("UPDATE pm_proposals"):
            proposal_id = params[4]
            record = self.proposals[proposal_id]
            record["status"] = params[0]
            record["approved_by"] = params[1]
            record["work_order_id"] = params[2]
            record["metadata"] = {**record.get("metadata", {}), **json.loads(params[3])}
            self._last_rows = [self._row(record)]
        elif normalized.startswith("SELECT wo_id"):
            requested_ids = set(params[0] or [])
            rows = [self._workorder_row(record) for record in self.workorders.values() if record["wo_id"] in requested_ids]
            rows.sort(key=lambda row: row[0], reverse=True)
            self._last_rows = rows
        elif normalized.startswith("SELECT status, workorder_created_at, handoff_completed_at, workorder_completed_at, metadata FROM workorders"):
            record = self.workorders.get(params[0])
            self._last_rows = [
                (
                    record["status"],
                    record["workorder_created_at"],
                    record["handoff_completed_at"],
                    record["workorder_completed_at"],
                    record["metadata"],
                )
            ] if record else []
        elif normalized.startswith("INSERT INTO workorders"):
            record = {
                "wo_id": params[0],
                "asset_id": params[1],
                "status": params[2],
                "title": params[3],
                "description": params[4],
                "priority": params[5],
                "metadata": json.loads(params[6]),
                "workorder_created_at": params[7],
                "handoff_completed_at": params[8],
                "workorder_completed_at": params[9],
            }
            self.workorders[record["wo_id"]] = record
            self._last_rows = []
        else:
            self._last_rows = []

    def fetchall(self):
        return list(self._last_rows)

    def fetchone(self):
        return self._last_rows[0] if self._last_rows else None

    @staticmethod
    def _row(record):
        return (
            record["proposal_id"],
            record["run_id"],
            record["recommendation_id"],
            record["event_id"],
            record["asset_id"],
            record["title"],
            record["rationale"],
            record["confidence"],
            record["status"],
            record["source_file"],
            record["proposed_by"],
            record["approved_by"],
            record["work_order_id"],
            record["metadata"],
        )

    @staticmethod
    def _workorder_row(record):
        return (
            record["wo_id"],
            record["asset_id"],
            record["status"],
            record["title"],
            record["priority"],
            record["workorder_created_at"],
            record["handoff_completed_at"],
            record["workorder_completed_at"],
            record["metadata"],
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self.closed = True


def _write_summary(base_dir, name="RUN-1.json", org_id=None, site_id=None):
    run_dir = base_dir / "2026-03-15"
    run_dir.mkdir(parents=True)
    path = run_dir / name
    context_meta = {"asset_id": "PUMP-101"}
    if org_id is not None:
        context_meta["org_id"] = org_id
    if site_id is not None:
        context_meta["site_id"] = site_id
    path.write_text(
        json.dumps(
            {
                "run_id": "RUN-1",
                "status": "ok",
                "recommendation_id": "REC-1",
                "event_id": "EVT-1",
                "model": {"name": "openai", "version": "gpt-4.1"},
                "structured": {
                    "title": "Inspect pump seal",
                    "hypothesis": ["Seal wear increasing vibration"],
                    "immediate_actions": ["Inspect seal housing"],
                    "pm_suggestions": ["Schedule seal replacement"],
                    "confidence": 0.81,
                },
                "context_meta": context_meta,
            }
        ),
        encoding="utf-8",
    )


def test_list_proposals_from_run_summaries(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: (_ for _ in ()).throw(RuntimeError("db unavailable")))

    client = TestClient(app)

    response = client.get("/api/v1/agents/pm/proposals", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["proposal_id"] == "REC-1"
    assert payload[0]["title"] == "Inspect pump seal"
    assert payload[0]["asset_id"] == "PUMP-101"
    assert payload[0]["attempt_count"] == 0
    assert payload[0]["attempts_remaining"] == 3
    assert payload[0]["max_attempts"] == 3
    assert payload[0]["retry_allowed"] is True
    assert payload[0]["admin_retry_required"] is False
    assert payload[0]["last_attempt_info"] == {}
    assert payload[0]["work_order_snapshot"] == {}
    assert payload[0]["connector_provenance_summary"]["proposal_id"] == "REC-1"
    assert payload[0]["connector_provenance_summary"]["connector_status"] == "pending"


def test_list_proposals_includes_retry_metadata_for_exceptions(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class IncompleteAdapter:
        backend_name = "incomplete"

        def create_work_order(self, recommendation):
            return {"status": "queued", "backend": self.backend_name, "response": {"status": "queued"}}

    class BadAdapter:
        backend_name = "bad"

        def create_work_order(self, recommendation):
            return "bad-payload"

    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    client = TestClient(app)

    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: IncompleteAdapter())
    assert client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"}).status_code == 202

    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: BadAdapter())
    assert client.post(
        "/api/v1/agents/pm/proposals/REC-1/approve",
        json={"admin_retry": True},
        headers={"x-user-id": "planner-2", "x-user-role": "maintainer"},
    ).status_code == 502

    response = client.get("/api/v1/agents/pm/proposals", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["proposal_id"] == "REC-1"
    assert payload[0]["handoff_state"] == "failure"
    assert payload[0]["attempt_count"] == 2
    assert payload[0]["attempts_remaining"] == 1
    assert payload[0]["max_attempts"] == 3
    assert payload[0]["retry_allowed"] is False
    assert payload[0]["admin_retry_required"] is False
    assert payload[0]["failure_summary"]["failure_class"] == "payload"
    assert payload[0]["failure_summary"]["retryable"] is False
    assert payload[0]["last_attempt_info"]["origin"] == "admin"
    assert payload[0]["last_attempt_info"]["handoff_state"] == "failure"
    assert payload[0]["last_attempt_info"]["error_message"] == "CMMS backend returned malformed payload"
    assert payload[0]["last_attempt_info"]["failure_summary"]["failure_class"] == "payload"


def test_analyze_persists_proposal_record(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)

    client = TestClient(app)

    response = client.post("/api/v1/agents/pm/advisor/analyze", json={"run_id": "RUN-1"}, headers={"x-user-id": "planner-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["proposal"]["proposal_id"] == "REC-1"
    assert payload["proposal"]["proposed_by"] == "planner-1"
    assert fake_connection.proposals["REC-1"]["status"] == "pending"


def test_analyze_requires_allowed_role(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    client = TestClient(app)
    response = client.post(
        "/api/v1/agents/pm/advisor/analyze",
        json={"run_id": "RUN-1"},
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "PM approval requires planner, maintainer, or admin role"


def test_approve_proposal_returns_422_for_unsupported_backend(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "sap")
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: FakeConnection())

    client = TestClient(app)

    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})

    assert response.status_code == 422
    assert "Unsupported CMMS backend" in response.json()["detail"]


def test_approve_proposal_with_mock_backend_persists_workorder(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "mock")
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)

    client = TestClient(app)

    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "dev-user"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["proposal_id"] == "REC-1"
    assert payload["status"] == "approved"
    assert payload["handoff_state"] == "success"
    assert payload["attempt_status"] == "success"
    assert payload["attempt_count"] == 1
    assert payload["attempts_remaining"] == 2
    assert payload["max_attempts"] == 3
    assert payload["retry_allowed"] is False
    assert payload["last_attempt_info"]["attempt_number"] == 1
    assert payload["detail"] == "PM proposal approved and handed off to the CMMS backend"
    assert payload["approved"] is True
    assert payload["reused_result"] is False
    assert payload["approved_by"] == "dev-user"
    assert payload["approved_at"]
    assert payload["proposal"]["approved_at"] == payload["approved_at"]
    assert payload["work_order"]["wo_id"] == "WO-REC-1"
    workorder_calls = [entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]]
    assert len(workorder_calls) == 1
    _query, params = workorder_calls[0]
    assert params[0] == "WO-REC-1"
    assert params[1] == "PUMP-101"
    assert params[2] == "DRAFT"
    workorder_metadata = fake_connection.workorders["WO-REC-1"]["metadata"]
    assert workorder_metadata["handoff"]["proposal_id"] == "REC-1"
    assert workorder_metadata["handoff"]["recommendation_id"] == "REC-1"
    assert workorder_metadata["handoff"]["approved_by"] == "dev-user"
    assert workorder_metadata["handoff"]["origin"] == "approval"
    assert workorder_metadata["handoff"]["handoff_state"] == "success"
    assert fake_connection.proposals["REC-1"]["status"] == "approved"
    assert fake_connection.proposals["REC-1"]["approved_by"] == "dev-user"
    assert fake_connection.proposals["REC-1"]["work_order_id"] == "WO-REC-1"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["approved_at"] == payload["approved_at"]
    assert fake_connection.closed is True


def test_connectors_endpoint_reports_supported_backends_and_required_fields(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "sap_pm")
    monkeypatch.setenv("MI_SAP_PM_BASE_URL", "https://sap.example.test")

    client = TestClient(app)
    response = client.get("/api/v1/agents/pm/connectors", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_backend"] == "sap_pm"
    assert payload["selected_backend"] == "sap_pm"
    assert [item["backend"] for item in payload["supported_backends"]] == ["maximo", "mock", "sap_pm", "servicenow"]
    sap_backend = next(item for item in payload["supported_backends"] if item["backend"] == "sap_pm")
    assert sap_backend["configured"] is True
    assert any(field["env_var"] == "MI_SAP_PM_BASE_URL" and field["required"] for field in sap_backend["config_fields"])
    assert {entry["phase"]: entry["statuses"] for entry in sap_backend["lifecycle_statuses"]}["active"] == ["CNF", "PCNF"]


def test_approve_proposal_with_sap_pm_backend_preserves_normalized_connector_metadata(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "sap_pm")
    monkeypatch.setenv("MI_SAP_PM_BASE_URL", "https://sap.example.test")
    monkeypatch.setenv("MI_SAP_PM_PLANT", "1710")
    monkeypatch.setenv("MI_SAP_PM_ORDER_TYPE", "PM02")
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)

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
        def __init__(self, *args, **kwargs):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr(sap_pm_mod.httpx, "Client", FakeClient)

    client = TestClient(app)
    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "dev-user"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["work_order"]["wo_id"] == "50000123"
    assert payload["work_order"]["lifecycle_phase"] == "completed"
    assert payload["connector_provenance_summary"]["backend"] == "sap_pm"
    assert payload["connector_provenance_summary"]["connector_lifecycle_phase"] == "completed"
    assert payload["last_attempt_info"]["connector_result"]["backend"] == "sap_pm"
    assert payload["last_attempt_info"]["connector_result"]["lifecycle_phase"] == "completed"
    assert payload["last_attempt_info"]["connector_result"]["request"]["Plant"] == "1710"
    assert payload["last_attempt_info"]["connector_result"]["request"]["OrderType"] == "PM02"
    workorder_metadata = fake_connection.workorders["50000123"]["metadata"]
    assert workorder_metadata["source"] == "agent-wo-bridge-sap_pm"
    assert workorder_metadata["handoff"]["backend"] == "sap_pm"
    assert workorder_metadata["request"]["Plant"] == "1710"
    assert workorder_metadata["response"]["OrderNumber"] == "50000123"


def test_approve_proposal_requires_allowed_role(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    client = TestClient(app)
    response = client.post(
        "/api/v1/agents/pm/proposals/REC-1/approve",
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "PM approval requires planner, maintainer, or admin role"


def test_list_proposals_includes_work_order_snapshot_after_handoff(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class SnapshotAdapter:
        backend_name = "snapshot"

        def create_work_order(self, recommendation):
            return {
                "wo_id": "WO-REC-1",
                "status": "DRAFT",
                "backend": self.backend_name,
                "workorder_created_at": "2026-03-15T10:05:00Z",
                "handoff_completed_at": "2026-03-15T10:05:30Z",
                "workorder_completed_at": None,
                "response": {"status": "DRAFT"},
            }

    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: SnapshotAdapter())

    client = TestClient(app)
    assert client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "dev-user"}).status_code == 200

    response = client.get("/api/v1/agents/pm/proposals", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["work_order_id"] == "WO-REC-1"
    assert payload[0]["work_order_snapshot"]["wo_id"] == "WO-REC-1"
    assert payload[0]["work_order_snapshot"]["status"] == "DRAFT"
    assert payload[0]["work_order_snapshot"]["workorder_created_at"] == "2026-03-15T10:05:00Z"
    assert payload[0]["work_order_snapshot"]["handoff_completed_at"] == "2026-03-15T10:05:30Z"
    assert payload[0]["work_order_snapshot"]["workorder_completed_at"] is None
    assert payload[0]["work_order_snapshot"]["lifecycle_phase"] == "handoff-complete"
    assert payload[0]["work_order_snapshot"]["terminal_state"] is False
    assert payload[0]["connector_provenance_summary"]["work_order_id"] == "WO-REC-1"
    assert payload[0]["connector_provenance_summary"]["work_order_lifecycle_phase"] == "handoff-complete"


def test_approve_proposal_returns_202_for_incomplete_handoff(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class IncompleteAdapter:
        backend_name = "incomplete"

        def create_work_order(self, recommendation):
            return {"status": "queued", "backend": self.backend_name, "response": {"status": "queued"}}

    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: IncompleteAdapter())

    client = TestClient(app)
    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "dev-user"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["handoff_state"] == "pending"
    assert payload["attempt_status"] == "pending"
    assert payload["attempt_count"] == 1
    assert payload["attempts_remaining"] == 2
    assert payload["max_attempts"] == 3
    assert payload["retry_allowed"] is True
    assert payload["last_attempt_info"]["attempt_number"] == 1
    assert payload["work_order"]["lifecycle_phase"] == "pending"
    assert payload["connector_provenance_summary"]["connector_lifecycle_phase"] == "pending"
    assert payload["detail"] == "PM proposal saved, but the CMMS handoff is still pending"
    assert payload["approved"] is False
    assert fake_connection.proposals["REC-1"]["status"] == "pending"
    assert fake_connection.proposals["REC-1"]["work_order_id"] is None
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["handoff_state"] == "pending"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["attempted_at"]
    workorder_calls = [entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]]
    assert workorder_calls == []


def test_approve_proposal_queues_offline_when_edge_mode_enabled(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    queue_path = tmp_path / "edge" / "command-buffer.sqlite3"
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setenv("MI_EDGE_MODE_ENABLED", "true")
    monkeypatch.setenv("MI_EDGE_COMMAND_BUFFER_PATH", str(queue_path))
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_INTERVAL_S", "0")
    fake_connection = FakeConnection()

    class OfflineAdapter:
        backend_name = "offline"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            raise pm_mod.CMMSUnavailableError("temporary outage")

    adapter = OfflineAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)

    client = TestClient(app)
    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued-offline"
    assert payload["handoff_state"] == "queued-offline"
    assert payload["attempt_status"] == "queued-offline"
    assert payload["detail"] == "PM proposal approved locally and queued for offline CMMS handoff"
    assert payload["approved"] is False
    assert payload["retry_allowed"] is False
    assert payload["admin_retry_required"] is False
    assert payload["attempt_count"] == 1
    assert payload["attempts_remaining"] == 2
    assert payload["work_order"]["status"] == "queued-offline"
    assert payload["work_order"]["queue_id"]
    assert payload["work_order"]["reason"] == "temporary outage"
    assert adapter.calls == 1
    assert fake_connection.proposals["REC-1"]["status"] == "queued-offline"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["handoff_state"] == "queued-offline"

    queue_module = _load_local_module(
        "maintenance_intelligence.runner.edge_command_buffer.runtime_check",
        Path("maintenance_intelligence/runner/edge_command_buffer.py"),
    )
    queued = queue_module.EdgeCommandBuffer(str(queue_path)).get_queued_command("REC-1")
    assert queued["proposal_id"] == "REC-1"
    assert queued["payload"]["handoff_context"]["approved_by"] == "planner-1"
    assert queued["payload"]["recommendation"]["asset_id"] == "PUMP-101"


def test_approve_proposal_with_servicenow_backend_returns_provenance_summary(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "servicenow")
    monkeypatch.setenv("MI_SERVICENOW_BASE_URL", "https://instance.service-now.test")
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)

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
        def __init__(self, *args, **kwargs):
            self.calls = []

        def post(self, url, json, headers):
            self.calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr(servicenow_mod.httpx, "Client", FakeClient)

    client = TestClient(app)
    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "dev-user"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["work_order"]["backend"] == "servicenow"
    assert payload["connector_provenance_summary"]["backend"] == "servicenow"
    assert payload["connector_provenance_summary"]["connector_lifecycle_phase"] == "active"
    assert payload["connector_provenance_summary"]["work_order_id"] == "WO0001234"
    assert fake_connection.proposals["REC-1"]["status"] == "approved"
    assert fake_connection.proposals["REC-1"]["work_order_id"] == "WO0001234"


def test_approve_proposal_reuses_existing_offline_queue_result(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    queue_path = tmp_path / "edge" / "command-buffer.sqlite3"
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setenv("MI_EDGE_MODE_ENABLED", "true")
    monkeypatch.setenv("MI_EDGE_COMMAND_BUFFER_PATH", str(queue_path))
    fake_connection = FakeConnection()

    class OfflineAdapter:
        backend_name = "offline"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            raise pm_mod.CMMSUnavailableError("temporary outage")

    adapter = OfflineAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)

    client = TestClient(app)
    first = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})
    second = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})

    assert first.status_code == 202
    assert second.status_code == 202
    second_payload = second.json()
    assert second_payload["status"] == "queued-offline"
    assert second_payload["reused_result"] is True
    assert second_payload["detail"] == "PM proposal already queued for offline handoff; returning the existing queue result"
    assert second_payload["retry_allowed"] is False
    assert adapter.calls == 1


def test_approve_proposal_returns_502_for_malformed_adapter_payload(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class BadAdapter:
        backend_name = "bad"

        def create_work_order(self, recommendation):
            return "bad-payload"

    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: BadAdapter())

    client = TestClient(app)
    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "dev-user"})

    assert response.status_code == 502
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["handoff_state"] == "failure"
    assert payload["attempt_status"] == "failure"
    assert payload["attempt_count"] == 1
    assert payload["attempts_remaining"] == 2
    assert payload["max_attempts"] == 3
    assert payload["retry_allowed"] is False
    assert payload["failure_summary"]["failure_class"] == "payload"
    assert payload["failure_summary"]["terminal"] is True
    assert payload["last_attempt_info"]["attempt_number"] == 1
    assert payload["last_attempt_info"]["failure_summary"]["failure_class"] == "payload"
    assert payload["detail"] == "CMMS backend returned malformed payload"
    assert payload["approved"] is False
    assert payload["proposal"]["approved_by"] == "dev-user"
    assert fake_connection.proposals["REC-1"]["status"] == "pending"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["detail"] == "CMMS backend returned malformed payload"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["handoff_state"] == "failure"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["failure_summary"]["failure_class"] == "payload"


def test_proposal_history_returns_recent_attempts_with_normalized_fields(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)

    class IncompleteAdapter:
        backend_name = "incomplete"

        def create_work_order(self, recommendation):
            return {"status": "queued", "backend": self.backend_name, "response": {"status": "queued"}}

    class BadAdapter:
        backend_name = "bad"

        def create_work_order(self, recommendation):
            return "bad-payload"

    client = TestClient(app)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: IncompleteAdapter())
    pending_response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})
    assert pending_response.status_code == 202

    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: BadAdapter())
    failed_response = client.post(
        "/api/v1/agents/pm/proposals/REC-1/approve",
        json={"admin_retry": True},
        headers={"x-user-id": "planner-2", "x-user-role": "maintainer"},
    )
    assert failed_response.status_code == 502

    history = client.get("/api/v1/agents/pm/proposals/REC-1/history", headers=READ_HEADERS)
    assert history.status_code == 200
    payload = history.json()
    assert payload["proposal_id"] == "REC-1"
    assert payload["last_approver"] == "planner-2"
    assert payload["handoff_state"] == "failure"
    assert payload["attempt_count"] == 2
    assert payload["attempts_remaining"] == 1
    assert payload["max_attempts"] == 3
    assert payload["retry_allowed"] is False
    assert payload["total_count"] == 2
    assert payload["page"] == 1
    assert payload["size"] == 3
    assert payload["has_more"] is False
    assert len(payload["attempts"]) == 2
    assert payload["attempts"][0]["approved_by"] == "planner-2"
    assert payload["attempts"][0]["handoff_state"] == "failure"
    assert payload["attempts"][0]["origin"] == "admin"
    assert payload["attempts"][0]["error_message"] == "CMMS backend returned malformed payload"
    assert payload["attempts"][0]["failure_summary"]["failure_class"] == "payload"
    assert payload["attempts"][1]["approved_by"] == "planner-1"
    assert payload["attempts"][1]["handoff_state"] == "pending"
    assert payload["attempts"][1]["origin"] == "approval"


def test_approve_proposal_is_idempotent_after_success(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class CountingAdapter:
        backend_name = "counting"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            return {"wo_id": "WO-REC-1", "status": "DRAFT", "backend": self.backend_name}

    adapter = CountingAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)

    client = TestClient(app)
    first = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})
    second = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["detail"] == "PM proposal already approved; returning the existing handoff result"
    assert second.json()["reused_result"] is True
    assert second.json()["attempt_count"] == 1
    assert second.json()["attempts_remaining"] == 2
    assert second.json()["retry_allowed"] is False
    assert adapter.calls == 1
    workorder_calls = [entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]]
    assert len(workorder_calls) == 1


def test_approve_proposal_retries_transient_failures_before_success(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_ATTEMPTS", "3")
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_INTERVAL_S", "0")
    fake_connection = FakeConnection()

    class FlakyAdapter:
        backend_name = "flaky"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            if self.calls < 3:
                raise pm_mod.CMMSUnavailableError("temporary outage")
            return {"wo_id": "WO-REC-1", "status": "DRAFT", "backend": self.backend_name}

    adapter = FlakyAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)

    client = TestClient(app)
    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["handoff_state"] == "success"
    assert payload["attempt_status"] == "success"
    assert payload["attempt_count"] == 3
    assert payload["attempts_remaining"] == 0
    assert payload["max_attempts"] == 3
    assert payload["retry_allowed"] is False
    assert payload["last_attempt_info"]["attempt_number"] == 3
    assert payload["reused_result"] is False
    assert adapter.calls == 3
    history = client.get("/api/v1/agents/pm/proposals/REC-1/history", headers=READ_HEADERS).json()
    assert len(history["attempts"]) == 3
    assert history["attempts"][0]["handoff_state"] == "success"
    assert history["attempts"][1]["handoff_state"] == "failure"
    assert history["attempts"][2]["handoff_state"] == "failure"
    assert history["attempts"][1]["failure_summary"]["failure_class"] == "transient"
    assert history["attempts"][1]["failure_summary"]["retryable"] is True


def test_approve_proposal_returns_final_failure_after_retry_exhaustion(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_INTERVAL_S", "0")
    fake_connection = FakeConnection()

    class DownAdapter:
        backend_name = "down"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            raise pm_mod.CMMSUnavailableError("temporary outage")

    adapter = DownAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)

    client = TestClient(app)
    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["handoff_state"] == "failure"
    assert payload["attempt_status"] == "failure"
    assert payload["attempt_count"] == 2
    assert payload["attempts_remaining"] == 1
    assert payload["max_attempts"] == 3
    assert payload["retry_allowed"] is True
    assert payload["failure_summary"]["failure_class"] == "transient"
    assert payload["failure_summary"]["retryable"] is True
    assert payload["last_attempt_info"]["attempt_number"] == 2
    assert payload["detail"] == "temporary outage"
    assert adapter.calls == 2
    history = client.get("/api/v1/agents/pm/proposals/REC-1/history", headers=READ_HEADERS).json()
    assert len(history["attempts"]) == 2
    assert all(attempt["handoff_state"] == "failure" for attempt in history["attempts"])
    assert all(attempt["failure_summary"]["failure_class"] == "transient" for attempt in history["attempts"])


def test_approve_proposal_blocks_retry_after_terminal_failure(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class BadAdapter:
        backend_name = "bad"

        def create_work_order(self, recommendation):
            return "bad-payload"

    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: BadAdapter())

    client = TestClient(app)
    first = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})
    second = client.post(
        "/api/v1/agents/pm/proposals/REC-1/approve",
        json={"admin_retry": True},
        headers={"x-user-id": "planner-2", "x-user-role": "maintainer"},
    )

    assert first.status_code == 502
    assert second.status_code == 409
    assert second.json()["detail"] == "Latest connector failure is terminal (payload); retry is not allowed"


def test_approve_proposal_retry_appends_history_and_creates_single_workorder(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class RetryThenSuccessAdapter:
        backend_name = "retry-then-success"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            if self.calls == 1:
                return {"status": "queued", "backend": self.backend_name, "response": {"status": "queued"}}
            return {"wo_id": "WO-REC-1", "status": "DRAFT", "backend": self.backend_name}

    adapter = RetryThenSuccessAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)

    client = TestClient(app)
    first = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})
    second = client.post("/api/v1/agents/pm/proposals/REC-1/approve", json={"admin_retry": True}, headers={"x-user-id": "planner-1", "x-user-role": "admin"})

    assert first.status_code == 202
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["attempt_count"] == 2
    assert second_payload["attempts_remaining"] == 1
    assert second_payload["retry_allowed"] is False
    history = client.get("/api/v1/agents/pm/proposals/REC-1/history", headers=READ_HEADERS)
    assert history.status_code == 200
    history_payload = history.json()
    assert len(history_payload["attempts"]) == 2
    assert history_payload["attempts"][0]["handoff_state"] == "success"
    assert history_payload["attempts"][0]["origin"] == "admin"
    assert history_payload["attempts"][1]["handoff_state"] == "pending"
    assert history_payload["attempts"][1]["origin"] == "approval"
    workorder_calls = [entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]]
    assert len(workorder_calls) == 1
    assert adapter.calls == 2


def test_manual_retry_requires_admin_role(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class PendingAdapter:
        backend_name = "pending"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            return {"status": "queued", "backend": self.backend_name, "response": {"status": "queued"}}

    adapter = PendingAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)
    client = TestClient(app)

    first = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1", "x-user-role": "planner"})
    blocked = client.post("/api/v1/agents/pm/proposals/REC-1/approve", json={"admin_retry": True}, headers={"x-user-id": "planner-1", "x-user-role": "planner"})
    missing_flag = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1", "x-user-role": "admin"})

    assert first.status_code == 202
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Admin retry requires admin or maintainer role"
    assert missing_flag.status_code == 403
    assert missing_flag.json()["detail"] == "Manual retries require an admin or maintainer role"
    assert adapter.calls == 1


def test_admin_retry_after_success_reuses_existing_workorder(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_connection = FakeConnection()

    class CountingAdapter:
        backend_name = "counting"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            return {"wo_id": "WO-REC-1", "status": "DRAFT", "backend": self.backend_name}

    adapter = CountingAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)
    client = TestClient(app)

    first = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1", "x-user-role": "planner"})
    second = client.post("/api/v1/agents/pm/proposals/REC-1/approve", json={"admin_retry": True}, headers={"x-user-id": "admin-1", "x-user-role": "admin"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["reused_result"] is True
    assert adapter.calls == 1
    history = client.get("/api/v1/agents/pm/proposals/REC-1/history", headers=READ_HEADERS).json()
    assert len(history["attempts"]) == 1
    assert history["attempts"][0]["origin"] == "approval"


def test_approve_proposal_rejects_requests_after_proposal_attempt_limit(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_ATTEMPTS", "5")
    monkeypatch.setenv("MI_PM_HANDOFF_MAX_ATTEMPTS_PER_PROPOSAL", "3")
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_INTERVAL_S", "0")
    fake_connection = FakeConnection()

    class DownAdapter:
        backend_name = "down"

        def __init__(self):
            self.calls = 0

        def create_work_order(self, recommendation):
            self.calls += 1
            raise pm_mod.CMMSUnavailableError("temporary outage")

    adapter = DownAdapter()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)
    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: adapter)

    client = TestClient(app)
    first = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})
    blocked = client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"})

    assert first.status_code == 503
    assert first.json()["attempt_count"] == 3
    assert first.json()["attempts_remaining"] == 0
    assert adapter.calls == 3
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "PM proposal reached the maximum of 3 handoff attempts"
    history = client.get("/api/v1/agents/pm/proposals/REC-1/history", headers=READ_HEADERS)
    assert history.status_code == 200
    assert history.json()["attempt_count"] == 3
    assert history.json()["attempts_remaining"] == 0
    assert history.json()["retry_allowed"] is False


def test_proposal_history_supports_paging_and_boundary_pages(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setenv("MI_PM_HANDOFF_RETRY_ATTEMPTS", "1")
    fake_connection = FakeConnection()
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)

    outcomes = iter(
        [
            {"status": "queued", "backend": "history", "response": {"status": "queued"}},
            pm_mod.CMMSUnavailableError("temporary outage"),
            {"wo_id": "WO-REC-1", "status": "DRAFT", "backend": "history"},
        ]
    )

    class SequenceAdapter:
        backend_name = "history"

        def create_work_order(self, recommendation):
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(pm_mod, "adapter_factory", lambda settings: SequenceAdapter())
    client = TestClient(app)

    assert client.post("/api/v1/agents/pm/proposals/REC-1/approve", headers={"x-user-id": "planner-1"}).status_code == 202
    assert client.post(
        "/api/v1/agents/pm/proposals/REC-1/approve",
        json={"admin_retry": True},
        headers={"x-user-id": "planner-2", "x-user-role": "admin"},
    ).status_code == 503
    assert client.post(
        "/api/v1/agents/pm/proposals/REC-1/approve",
        json={"admin_retry": True},
        headers={"x-user-id": "planner-3", "x-user-role": "admin"},
    ).status_code == 200

    first_page = client.get("/api/v1/agents/pm/proposals/REC-1/history?page=1&size=2", headers=READ_HEADERS)
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert first_payload["total_count"] == 3
    assert first_payload["page"] == 1
    assert first_payload["size"] == 2
    assert first_payload["has_more"] is True
    assert [attempt["approved_by"] for attempt in first_payload["attempts"]] == ["planner-3", "planner-2"]

    second_page = client.get("/api/v1/agents/pm/proposals/REC-1/history?page=2&size=2", headers=READ_HEADERS)
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["total_count"] == 3
    assert second_payload["page"] == 2
    assert second_payload["size"] == 2
    assert second_payload["has_more"] is False
    assert len(second_payload["attempts"]) == 1
    assert second_payload["attempts"][0]["approved_by"] == "planner-1"

    empty_page = client.get("/api/v1/agents/pm/proposals/REC-1/history?page=3&size=2", headers=READ_HEADERS)
    assert empty_page.status_code == 200
    empty_payload = empty_page.json()
    assert empty_payload["attempts"] == []
    assert empty_payload["total_count"] == 3
    assert empty_payload["has_more"] is False


def test_proposal_history_validates_page_and_size_limits(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    client = TestClient(app)

    bad_page = client.get("/api/v1/agents/pm/proposals/REC-1/history?page=0&size=3", headers=READ_HEADERS)
    bad_size_low = client.get("/api/v1/agents/pm/proposals/REC-1/history?page=1&size=0", headers=READ_HEADERS)
    bad_size_high = client.get("/api/v1/agents/pm/proposals/REC-1/history?page=1&size=26", headers=READ_HEADERS)

    assert bad_page.status_code == 422
    assert bad_size_low.status_code == 422
    assert bad_size_high.status_code == 422


def test_proposal_read_endpoints_require_authenticated_identity(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)

    client = TestClient(app)

    proposals = client.get("/api/v1/agents/pm/proposals")
    history = client.get("/api/v1/agents/pm/proposals/REC-1/history")

    assert proposals.status_code == 403
    assert proposals.json()["detail"] == "PM proposal reads require an authenticated identity"
    assert history.status_code == 403
    assert history.json()["detail"] == "PM proposal reads require an authenticated identity"


def test_approve_proposal_rejects_cross_tenant_org_scope(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries, org_id="demo-org")
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")

    client = TestClient(app)
    response = client.post(
        "/api/v1/agents/pm/proposals/REC-1/approve",
        headers={
            "x-user-id": "planner-1",
            "x-user-role": "planner",
            "x-org-id": "other-org",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "PM approval is not authorized for this organization"