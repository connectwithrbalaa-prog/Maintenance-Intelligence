import json

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import pm_advisor as pm_mod


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

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
        self.proposals = {}
        self._last_rows = []
        self.closed = False

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
        elif normalized.startswith("UPDATE pm_proposals"):
            proposal_id = params[4]
            record = self.proposals[proposal_id]
            record["status"] = params[0]
            record["approved_by"] = params[1]
            record["work_order_id"] = params[2]
            record["metadata"] = {**record.get("metadata", {}), **json.loads(params[3])}
            self._last_rows = [self._row(record)]
        elif normalized.startswith("SELECT proposal_id"):
            self._last_rows = [self._row(record) for record in self.proposals.values()]
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


def test_maximo_smoke_approval_flow(httpserver, monkeypatch, tmp_path):
    summaries = tmp_path / "outputs"
    _write_summary(summaries)
    fake_connection = FakeConnection()

    httpserver.expect_request("/oslc/os/mxwo", method="POST").respond_with_json(
        {"wonum": "MX-1001", "status": "WAPPR"}
    )

    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(summaries))
    monkeypatch.setenv("MI_PM_CONNECTOR_BACKEND", "maximo")
    monkeypatch.setenv("MI_MAXIMO_BASE_URL", httpserver.url_for(""))
    monkeypatch.setenv("MI_MAXIMO_SITE", "PLANT1")
    monkeypatch.setenv("MI_MAXIMO_API_KEY", "secret")
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(pm_mod, "connection_factory", lambda _dsn: fake_connection)

    client = TestClient(app)

    analyze_response = client.post(
        "/api/v1/agents/pm/advisor/analyze",
        json={"run_id": "RUN-1"},
        headers={"x-user-id": "planner-1"},
    )
    assert analyze_response.status_code == 200

    approve_response = client.post(
        "/api/v1/agents/pm/proposals/REC-1/approve",
        headers={"x-user-id": "approver-1"},
    )

    assert approve_response.status_code == 200
    payload = approve_response.json()
    assert payload["handoff_state"] == "success"
    assert payload["approved_by"] == "approver-1"
    assert payload["work_order"]["wo_id"] == "MX-1001"
    assert payload["work_order"]["status"] == "WAPPR"
    assert fake_connection.proposals["REC-1"]["status"] == "approved"
    assert fake_connection.proposals["REC-1"]["work_order_id"] == "MX-1001"
    assert fake_connection.proposals["REC-1"]["approved_by"] == "approver-1"
    httpserver.check_assertions()
