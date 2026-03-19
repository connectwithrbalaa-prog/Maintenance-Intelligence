import json

from maintenance_intelligence.cmms.adapter import CMMSUnavailableError
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.edge_command_buffer import EdgeCommandBuffer
from maintenance_intelligence.services import wo_bridge as wo_bridge_mod


class FakeMessage:
    def __init__(self, value):
        self.value = value


class FakeConsumer:
    def __init__(self, messages):
        self._messages = [FakeMessage(message) for message in messages]
        self.closed = False

    def __iter__(self):
        return iter(self._messages)

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.executed = connection.executed
        self.rows = []

    def execute(self, query, params):
        self.executed.append((query, params))
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT status, workorder_created_at, handoff_completed_at, workorder_completed_at, metadata FROM workorders"):
            record = self.connection.workorders.get(params[0])
            self.rows = [
                (
                    record["status"],
                    record["workorder_created_at"],
                    record["handoff_completed_at"],
                    record["workorder_completed_at"],
                    record["metadata"],
                )
            ] if record else []
            return
        if normalized.startswith("SELECT status, approved_by, work_order_id, metadata FROM pm_proposals"):
            record = self.connection.proposals.get(params[0])
            self.rows = [
                (
                    record["status"],
                    record["approved_by"],
                    record["work_order_id"],
                    record["metadata"],
                )
            ] if record else []
            return
        if normalized.startswith("INSERT INTO workorders"):
            self.connection.workorders[params[0]] = {
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
            return
        if normalized.startswith("UPDATE pm_proposals SET status = %s, approved_by = %s, work_order_id = %s, metadata = %s::jsonb WHERE proposal_id = %s"):
            record = self.connection.proposals.get(params[4]) or {
                "proposal_id": params[4],
                "status": None,
                "approved_by": None,
                "work_order_id": None,
                "metadata": {},
            }
            record["status"] = params[0]
            record["approved_by"] = params[1]
            record["work_order_id"] = params[2]
            record["metadata"] = json.loads(params[3])
            self.connection.proposals[params[4]] = record

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.closed = False
        self.workorders = {}
        self.proposals = {}

    def cursor(self):
        return FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self.closed = True


class FakeAdapter:
    backend_name = "mock"

    def __init__(self):
        self.calls = []

    def create_work_order(self, recommendation):
        self.calls.append(recommendation)
        return {
            "wo_id": "WO-REC-1234",
            "status": "COMP",
            "backend": "mock",
            "created_at": "2026-03-15T12:00:00Z",
            "request": {"asset_id": recommendation.get("asset_id")},
            "response": {
                "source": "mock",
                "statusdate": "2026-03-15T12:05:00Z",
                "actfinish": "2026-03-15T13:00:00Z",
            },
        }


def test_wo_bridge_loop_invokes_adapter_and_persists_result():
    fake_connection = FakeConnection()
    fake_consumer = FakeConsumer(
        [
            {
                "recommendation": {
                    "id": "REC-12345678",
                    "asset_id": "PUMP-101",
                    "title": "Inspect seal",
                    "rationale": "Elevated vibration",
                    "priority": "HIGH",
                }
            }
        ]
    )
    fake_adapter = FakeAdapter()

    wo_bridge_mod.wo_bridge(
        kafka_bootstrap="kafka:9092",
        pg_dsn="dbname=test",
        settings=Settings(),
        connection_factory=lambda _dsn: fake_connection,
        consumer_factory=lambda *args, **kwargs: fake_consumer,
        adapter_factory=lambda settings: fake_adapter,
    )

    assert len(fake_adapter.calls) == 1
    assert fake_adapter.calls[0]["asset_id"] == "PUMP-101"
    workorder_calls = [entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]]
    assert len(workorder_calls) == 1
    _query, params = workorder_calls[0]
    assert params[0] == "WO-REC-1234"
    assert params[1] == "PUMP-101"
    assert params[2] == "COMP"
    metadata = json.loads(params[6])
    assert metadata["source"] == "agent-wo-bridge-mock"
    assert metadata["request"]["asset_id"] == "PUMP-101"
    assert metadata["handoff"]["recommendation_id"] == "REC-12345678"
    assert metadata["handoff"]["origin"] == "bridge"
    assert metadata["handoff"]["wo_id"] == "WO-REC-1234"
    assert metadata["handoff"]["lifecycle_phase"] == "completed"
    assert metadata["handoff"]["terminal_state"] is True
    assert params[7] == "2026-03-15T12:00:00Z"
    assert params[8] == "2026-03-15T12:05:00Z"
    assert params[9] == "2026-03-15T13:00:00Z"
    assert fake_consumer.closed is True
    assert fake_connection.closed is True


def test_persist_work_order_uses_guarded_upsert_for_canonical_timestamps():
    fake_connection = FakeConnection()

    wo_bridge_mod.persist_work_order(
        fake_connection,
        {
            "asset_id": "PUMP-101",
            "title": "Inspect seal",
            "rationale": "Elevated vibration",
            "priority": "HIGH",
        },
        {
            "wo_id": "WO-REC-1234",
            "status": "COMP",
            "backend": "mock",
            "created_at": "2026-03-15T12:00:00Z",
            "handoff_complete": True,
            "response": {"statusdate": "2026-03-15T12:05:00Z", "actfinish": "2026-03-15T13:00:00Z"},
            "raw_response": {"statusdate": "2026-03-15T12:05:00Z", "actfinish": "2026-03-15T13:00:00Z"},
        },
    )

    query, params = [entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]][0]
    assert "ON CONFLICT (wo_id) DO UPDATE SET" in query
    assert "workorder_created_at = COALESCE(workorders.workorder_created_at, EXCLUDED.workorder_created_at)" in query
    assert "handoff_completed_at = COALESCE(workorders.handoff_completed_at, EXCLUDED.handoff_completed_at)" in query
    assert "workorder_completed_at = COALESCE(workorders.workorder_completed_at, EXCLUDED.workorder_completed_at)" in query
    metadata = json.loads(params[6])
    assert metadata["handoff"]["handoff_state"] == "success"
    assert metadata["handoff"]["backend"] == "mock"
    assert metadata["handoff"]["lifecycle"]["phase"] == "completed"
    assert params[7] == "2026-03-15T12:00:00Z"
    assert params[8] == "2026-03-15T12:05:00Z"
    assert params[9] == "2026-03-15T13:00:00Z"


def test_persist_work_order_preserves_terminal_state_on_regressive_update():
    fake_connection = FakeConnection()
    fake_connection.workorders["WO-REC-1234"] = {
        "wo_id": "WO-REC-1234",
        "asset_id": "PUMP-101",
        "status": "COMP",
        "title": "Inspect seal",
        "description": "Elevated vibration",
        "priority": "HIGH",
        "metadata": {"handoff": {"status_after": "COMP"}},
        "workorder_created_at": "2026-03-15T12:00:00Z",
        "handoff_completed_at": "2026-03-15T12:05:00Z",
        "workorder_completed_at": "2026-03-15T13:00:00Z",
    }

    wo_bridge_mod.persist_work_order(
        fake_connection,
        {"asset_id": "PUMP-101", "title": "Inspect seal", "rationale": "Elevated vibration", "priority": "HIGH"},
        {"wo_id": "WO-REC-1234", "status": "DRAFT", "backend": "mock", "handoff_complete": True, "response": {"status": "DRAFT"}},
    )

    record = fake_connection.workorders["WO-REC-1234"]
    assert record["status"] == "COMP"
    assert record["workorder_completed_at"] == "2026-03-15T13:00:00Z"
    assert record["metadata"]["handoff"]["status_before"] == "COMP"
    assert record["metadata"]["handoff"]["status_after"] == "COMP"
    assert record["metadata"]["handoff"]["lifecycle_phase"] == "completed"
    assert record["metadata"]["handoff"]["lifecycle"]["terminal"] is True


def test_persist_work_order_promotes_terminal_transition_when_completion_arrives():
    fake_connection = FakeConnection()
    fake_connection.workorders["WO-REC-1234"] = {
        "wo_id": "WO-REC-1234",
        "asset_id": "PUMP-101",
        "status": "DRAFT",
        "title": "Inspect seal",
        "description": "Elevated vibration",
        "priority": "HIGH",
        "metadata": {"handoff": {"status_after": "DRAFT"}},
        "workorder_created_at": "2026-03-15T12:00:00Z",
        "handoff_completed_at": "2026-03-15T12:05:00Z",
        "workorder_completed_at": None,
    }

    wo_bridge_mod.persist_work_order(
        fake_connection,
        {"asset_id": "PUMP-101", "title": "Inspect seal", "rationale": "Elevated vibration", "priority": "HIGH"},
        {
            "wo_id": "WO-REC-1234",
            "status": "COMP",
            "backend": "mock",
            "handoff_complete": True,
            "response": {"statusdate": "2026-03-15T12:05:00Z", "actfinish": "2026-03-15T13:00:00Z"},
        },
    )

    record = fake_connection.workorders["WO-REC-1234"]
    assert record["status"] == "COMP"
    assert record["workorder_completed_at"] == "2026-03-15T13:00:00Z"
    assert record["metadata"]["handoff"]["status_before"] == "DRAFT"
    assert record["metadata"]["handoff"]["status_after"] == "COMP"
    assert record["metadata"]["handoff"]["lifecycle_phase"] == "completed"
    assert record["metadata"]["handoff"]["lifecycle"]["phase"] == "completed"


def test_wo_bridge_replays_queued_edge_commands_before_live_messages(tmp_path):
    fake_connection = FakeConnection()
    fake_connection.proposals["REC-QUEUED"] = {
        "proposal_id": "REC-QUEUED",
        "status": "queued-offline",
        "approved_by": "planner-1",
        "work_order_id": None,
        "metadata": {
            "approval": {
                "approved_by": "planner-1",
                "attempted_at": "2026-03-15T10:00:00Z",
                "handoff_state": "queued-offline",
            },
            "approval_attempts": [
                {
                    "attempt_number": 1,
                    "approved_by": "planner-1",
                    "attempted_at": "2026-03-15T10:00:00Z",
                    "handoff_state": "queued-offline",
                    "origin": "approval",
                    "result": "pending",
                    "connector_result": {"status": "queued-offline", "queue_id": 1},
                    "error_message": "temporary outage",
                }
            ],
        },
    }
    queue_path = tmp_path / "edge-command.sqlite3"
    command_queue = EdgeCommandBuffer(str(queue_path))
    command_queue.enqueue_command(
        "REC-QUEUED",
        {
            "proposal_id": "REC-QUEUED",
            "recommendation_id": "REC-QUEUED",
            "recommendation": {
                "id": "REC-QUEUED",
                "asset_id": "PUMP-101",
                "title": "Replay queued handoff",
                "rationale": "Buffered approval",
                "priority": "HIGH",
            },
            "handoff_context": {
                "proposal_id": "REC-QUEUED",
                "recommendation_id": "REC-QUEUED",
                "approved_by": "planner-1",
                "origin": "approval",
            },
        },
        error="temporary outage",
    )
    fake_consumer = FakeConsumer(
        [
            {
                "recommendation": {
                    "id": "REC-LIVE",
                    "asset_id": "PUMP-202",
                    "title": "Inspect live seal",
                    "rationale": "Elevated vibration",
                    "priority": "HIGH",
                }
            }
        ]
    )
    fake_adapter = FakeAdapter()
    settings = Settings(edge_mode_enabled=True, edge_command_buffer_path=str(queue_path))

    wo_bridge_mod.wo_bridge(
        kafka_bootstrap="kafka:9092",
        pg_dsn="dbname=test",
        settings=settings,
        connection_factory=lambda _dsn: fake_connection,
        consumer_factory=lambda *args, **kwargs: fake_consumer,
        adapter_factory=lambda settings: fake_adapter,
    )

    assert [call["id"] for call in fake_adapter.calls] == ["REC-QUEUED", "REC-LIVE"]
    assert command_queue.snapshot()["queued_command_count"] == 0
    assert command_queue.snapshot()["total_replayed_commands"] == 1
    assert fake_connection.proposals["REC-QUEUED"]["status"] == "approved"
    assert fake_connection.proposals["REC-QUEUED"]["work_order_id"] == "WO-REC-1234"
    assert fake_connection.proposals["REC-QUEUED"]["metadata"]["approval"]["handoff_state"] == "success"


def test_replay_failure_records_normalized_failure_summary(tmp_path):
    fake_connection = FakeConnection()
    fake_connection.proposals["REC-FAIL"] = {
        "proposal_id": "REC-FAIL",
        "status": "queued-offline",
        "approved_by": "planner-1",
        "work_order_id": None,
        "metadata": {},
    }
    queue_path = tmp_path / "edge-command.sqlite3"
    command_queue = EdgeCommandBuffer(str(queue_path))
    command_queue.enqueue_command(
        "REC-FAIL",
        {
            "proposal_id": "REC-FAIL",
            "recommendation_id": "REC-FAIL",
            "recommendation": {
                "id": "REC-FAIL",
                "asset_id": "PUMP-101",
                "title": "Replay queued handoff",
                "rationale": "Buffered approval",
                "priority": "HIGH",
            },
            "handoff_context": {
                "proposal_id": "REC-FAIL",
                "recommendation_id": "REC-FAIL",
                "approved_by": "planner-1",
                "origin": "approval",
            },
        },
        error="temporary outage",
    )

    class DownAdapter:
        backend_name = "offline"

        def create_work_order(self, recommendation):
            raise CMMSUnavailableError("temporary outage")

    outcome = wo_bridge_mod._replay_edge_command_queue(fake_connection, DownAdapter(), command_queue)

    assert outcome == {"replayed": 0, "error": "temporary outage"}
    attempt = fake_connection.proposals["REC-FAIL"]["metadata"]["approval_attempts"][0]
    assert attempt["handoff_state"] == "queued-offline"
    assert attempt["failure_summary"]["failure_class"] == "transient"
    assert attempt["failure_summary"]["retryable"] is True


def test_with_pg_retries_then_succeeds(monkeypatch):
    attempts = {"count": 0}
    sleeps = []
    sentinel_conn = object()

    def fake_connect(_dsn):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary db outage")
        return sentinel_conn

    monkeypatch.setattr(wo_bridge_mod.psycopg2, "connect", fake_connect)
    monkeypatch.setattr(wo_bridge_mod.time, "sleep", lambda seconds: sleeps.append(seconds))

    conn = wo_bridge_mod.with_pg("dbname=test", retry_interval_s=0.01, max_attempts=5)

    assert conn is sentinel_conn
    assert attempts["count"] == 3
    assert sleeps == [0.01, 0.01]


def test_with_pg_raises_after_max_attempts(monkeypatch):
    attempts = {"count": 0}
    sleeps = []

    def fake_connect(_dsn):
        attempts["count"] += 1
        raise RuntimeError("db down")

    monkeypatch.setattr(wo_bridge_mod.psycopg2, "connect", fake_connect)
    monkeypatch.setattr(wo_bridge_mod.time, "sleep", lambda seconds: sleeps.append(seconds))

    try:
        wo_bridge_mod.with_pg("dbname=test", retry_interval_s=0.02, max_attempts=4)
        assert False, "Expected with_pg to raise after max attempts"
    except RuntimeError as exc:
        assert str(exc) == "db down"

    assert attempts["count"] == 4
    assert sleeps == [0.02, 0.02, 0.02]