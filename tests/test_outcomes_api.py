import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import outcomes as outcomes_mod


class FakeCursor:
    def __init__(self, handlers):
        self.handlers = handlers
        self.fetch_rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql):
        for marker, handler in self.handlers.items():
            if marker in sql:
                result = handler()
                self.fetch_rows = result or []
                return
        raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchall(self):
        return self.fetch_rows


class FakeConnection:
    def __init__(self, handlers):
        self.handlers = handlers
        self.rollback_calls = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self.handlers)

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.closed = True


def test_outcomes_endpoint_returns_partial_placeholders_when_one_query_fails(monkeypatch):
    now = datetime.now(timezone.utc)
    fake_conn = FakeConnection(
        {
            "FROM rca_feedback": lambda: [("accept", 2), ("reject", 1)],
            "FROM workorders w\n                    JOIN events e": lambda: (_ for _ in ()).throw(RuntimeError("join unavailable")),
            "GROUP BY w.asset_id": lambda: [("PUMP-101", 4)],
        }
    )
    monkeypatch.setattr(outcomes_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/rca-outcomes?window=30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["window_days"] == 30
    assert payload["feedback_counts"] == {"accept": 2, "reject": 1, "edited": 0}
    assert payload["feedback_total"] == 3
    assert payload["acceptance_rate"] == 2 / 3
    assert payload["ttr_seconds_avg"] is None
    assert payload["mtbf_seconds_avg"] is None
    assert payload["mttr_seconds_avg"] is None
    assert payload["top_assets_by_wo_volume"] == [{"asset_id": "PUMP-101", "count": 4}]
    assert payload["warnings"] == ["ttr aggregation unavailable: join unavailable"]
    assert "mtbf_seconds_avg" in payload["placeholders"]
    assert fake_conn.rollback_calls == 1
    assert fake_conn.closed is True


def test_outcomes_csv_includes_stable_placeholder_rows(monkeypatch):
    monkeypatch.setattr(
        outcomes_mod,
        "rca_outcomes",
        lambda window=30: {
            "window_days": window,
            "status": "partial",
            "warnings": ["missing lifecycle timestamps"],
            "feedback_counts": {"accept": 1, "reject": 0, "edited": 2},
            "feedback_total": 3,
            "acceptance_rate": 1 / 3,
            "ttr_seconds_avg": None,
            "mtbf_seconds_avg": None,
            "mttr_seconds_avg": None,
            "top_assets_by_wo_volume": [{"asset_id": "PUMP-7", "count": 2}],
            "placeholders": {},
        },
    )

    client = TestClient(app)
    response = client.get("/api/v1/reports/rca-outcomes/csv?window=30")

    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    metrics = {row["metric"]: row["value"] for row in rows}
    assert metrics["feedback_accept"] == "1"
    assert metrics["feedback_reject"] == "0"
    assert metrics["feedback_edited"] == "2"
    assert metrics["feedback_total"] == "3"
    assert metrics["report_status"] == "partial"
    assert metrics["warning_count"] == "1"
    assert metrics["acceptance_rate"]
    assert metrics["ttr_seconds_avg"] == ""
    assert metrics["mtbf_seconds_avg"] == ""
    assert metrics["mttr_seconds_avg"] == ""
    assert metrics["top_asset_PUMP-7_wo_count"] == "2"