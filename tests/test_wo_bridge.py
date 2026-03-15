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
    def __init__(self, executed):
        self.executed = executed

    def execute(self, query, params):
        self.executed.append((query, params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.closed = False

    def cursor(self):
        return FakeCursor(self.executed)

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
            "status": "DRAFT",
            "backend": "mock",
            "created_at": "2026-03-15T12:00:00Z",
            "request": {"asset_id": recommendation.get("asset_id")},
            "response": {"source": "mock"},
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
    assert len(fake_connection.executed) == 1
    _query, params = fake_connection.executed[0]
    assert params[0] == "WO-REC-1234"
    assert params[1] == "PUMP-101"
    assert params[2] == "DRAFT"
    metadata = json.loads(params[6])
    assert metadata["source"] == "agent-wo-bridge-mock"
    assert metadata["request"]["asset_id"] == "PUMP-101"
    assert fake_consumer.closed is True
    assert fake_connection.closed is True