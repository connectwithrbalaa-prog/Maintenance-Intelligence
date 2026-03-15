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
_load_local_module("maintenance_intelligence.api.metrics", Path("maintenance_intelligence/api/metrics.py"))
identity_mod = _load_local_module("maintenance_intelligence.api.middleware.identity", Path("maintenance_intelligence/api/middleware/identity.py"))
_load_local_module("maintenance_intelligence.cmms.adapter", Path("maintenance_intelligence/cmms/adapter.py"))
_load_local_module("maintenance_intelligence.cmms.mock", Path("maintenance_intelligence/cmms/mock.py"))
_load_local_module("maintenance_intelligence.cmms.maximo", Path("maintenance_intelligence/cmms/maximo.py"))
_load_local_module("maintenance_intelligence.services.wo_bridge", Path("maintenance_intelligence/services/wo_bridge.py"))
pm_mod = _load_local_module("maintenance_intelligence.api.pm_advisor", Path("maintenance_intelligence/api/pm_advisor.py"))
app = FastAPI()
identity_mod.install_identity_middleware(app)
app.include_router(pm_mod.router)


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
        elif normalized.startswith("INSERT INTO workorders"):
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self.closed = True


def _write_summary(base_dir, name="RUN-1.json"):
    run_dir = base_dir / "2026-03-15"
    run_dir.mkdir(parents=True)
    path = run_dir / name
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
                "context_meta": {"asset_id": "PUMP-101"},
            }
        ),
        encoding="utf-8",
    )


def test_list_proposals_from_run_summaries(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: (_ for _ in ()).throw(RuntimeError("db unavailable")))

    client = TestClient(app)

    response = client.get("/api/v1/agents/pm/proposals")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["proposal_id"] == "REC-1"
    assert payload[0]["title"] == "Inspect pump seal"
    assert payload[0]["asset_id"] == "PUMP-101"


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


def test_approve_proposal_returns_422_for_unsupported_backend(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "sap")
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: FakeConnection())

    client = TestClient(app)

    response = client.post("/api/v1/agents/pm/proposals/REC-1/approve")

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
    assert payload["detail"] == "PM proposal approved and handed off to the CMMS backend"
    assert payload["approved"] is True
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
    assert fake_connection.proposals["REC-1"]["status"] == "approved"
    assert fake_connection.proposals["REC-1"]["approved_by"] == "dev-user"
    assert fake_connection.proposals["REC-1"]["work_order_id"] == "WO-REC-1"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["approved_at"] == payload["approved_at"]
    assert fake_connection.closed is True


def test_approve_proposal_returns_202_for_incomplete_handoff(monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
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
    assert payload["detail"] == "PM proposal saved, but the CMMS handoff is still pending"
    assert payload["approved"] is False
    assert fake_connection.proposals["REC-1"]["status"] == "pending"
    assert fake_connection.proposals["REC-1"]["work_order_id"] is None
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["handoff_state"] == "pending"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["attempted_at"]
    workorder_calls = [entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]]
    assert workorder_calls == []


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
    assert payload["detail"] == "CMMS backend returned malformed payload"
    assert payload["approved"] is False
    assert payload["proposal"]["approved_by"] == "dev-user"
    assert fake_connection.proposals["REC-1"]["status"] == "pending"
    assert fake_connection.proposals["REC-1"]["metadata"]["approval"]["detail"] == "CMMS backend returned malformed payload"