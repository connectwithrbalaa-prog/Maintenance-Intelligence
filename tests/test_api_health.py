from types import SimpleNamespace

import maintenance_intelligence.api.health as health_mod
from fastapi.testclient import TestClient
from maintenance_intelligence.api.main import app


class FakeCursor:
    def execute(self, query):
        assert query == "SELECT 1"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return FakeCursor()

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

def test_health_basic():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_health_deep_reports_ok_when_pg_kafka_and_lag_are_healthy(monkeypatch):
    fake_conn = FakeConnection()

    monkeypatch.setattr(health_mod, "Settings", lambda: SimpleNamespace(pg_dsn="dsn", kafka_bootstrap="kafka:9092"))
    monkeypatch.setattr(health_mod.psycopg2, "connect", lambda dsn: fake_conn)
    monkeypatch.setattr(health_mod, "KafkaAdminClient", lambda **kwargs: SimpleNamespace(list_topics=lambda: ["topic-a"]))
    monkeypatch.setattr(health_mod, "compute_kafka_lag", lambda *args, **kwargs: {"_summary": {"total_lag": 12}})

    payload = health_mod.healthz(deep=True)

    assert payload["status"] == "ok"
    assert payload["pg"] == "ok"
    assert payload["kafka"] == "ok"
    assert payload["kafka_lag"] == {"_summary": {"total_lag": 12}}
    assert fake_conn.closed is True


def test_health_deep_degrades_when_dependencies_fail_or_lag_is_unknown(monkeypatch):
    monkeypatch.setattr(health_mod, "Settings", lambda: SimpleNamespace(pg_dsn="dsn", kafka_bootstrap="kafka:9092"))
    monkeypatch.setattr(health_mod.psycopg2, "connect", lambda dsn: (_ for _ in ()).throw(RuntimeError("pg down")))
    monkeypatch.setattr(health_mod, "KafkaAdminClient", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("kafka down")))
    monkeypatch.setattr(health_mod, "compute_kafka_lag", lambda *args, **kwargs: {"_summary": {"total_lag": None}})

    payload = health_mod.healthz(deep=True)

    assert payload["status"] == "degraded"
    assert payload["pg"] == "error: pg down"
    assert payload["kafka"] == "error: kafka down"
    assert payload["kafka_lag"] == {"_summary": {"total_lag": None}}
