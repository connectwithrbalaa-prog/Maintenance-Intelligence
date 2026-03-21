import json

from maintenance_intelligence.runner.config import Settings
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
        if normalized.startswith(
            "SELECT status, workorder_created_at, handoff_completed_at, workorder_completed_at, metadata FROM workorders"
        ):
            record = self.connection.workorders.get(params[0])
            self.rows = (
                [
                    (
                        record["status"],
                        record["workorder_created_at"],
                        record["handoff_completed_at"],
                        record["workorder_completed_at"],
                        record["metadata"],
                    )
                ]
                if record
                else []
            )
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
    workorder_calls = [
        entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]
    ]
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
            "raw_response": {
                "statusdate": "2026-03-15T12:05:00Z",
                "actfinish": "2026-03-15T13:00:00Z",
            },
        },
    )

    query, params = [
        entry for entry in fake_connection.executed if "INSERT INTO workorders" in entry[0]
    ][0]
    assert "ON CONFLICT (wo_id) DO UPDATE SET" in query
    assert (
        "workorder_created_at = COALESCE(workorders.workorder_created_at, EXCLUDED.workorder_created_at)"
        in query
    )
    assert (
        "handoff_completed_at = COALESCE(workorders.handoff_completed_at, EXCLUDED.handoff_completed_at)"
        in query
    )
    assert (
        "workorder_completed_at = COALESCE(workorders.workorder_completed_at, EXCLUDED.workorder_completed_at)"
        in query
    )
    metadata = json.loads(params[6])
    assert metadata["handoff"]["handoff_state"] == "success"
    assert metadata["handoff"]["backend"] == "mock"
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
        {
            "asset_id": "PUMP-101",
            "title": "Inspect seal",
            "rationale": "Elevated vibration",
            "priority": "HIGH",
        },
        {
            "wo_id": "WO-REC-1234",
            "status": "DRAFT",
            "backend": "mock",
            "handoff_complete": True,
            "response": {"status": "DRAFT"},
        },
    )

    record = fake_connection.workorders["WO-REC-1234"]
    assert record["status"] == "COMP"
    assert record["workorder_completed_at"] == "2026-03-15T13:00:00Z"
    assert record["metadata"]["handoff"]["status_before"] == "COMP"
    assert record["metadata"]["handoff"]["status_after"] == "COMP"
    assert record["metadata"]["handoff"]["lifecycle_phase"] == "completed"


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
