import csv
import io
from datetime import datetime, timezone

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
    fake_conn = FakeConnection(
        {
            "SELECT action, COUNT(*) FROM rca_feedback": lambda: [("accept", 2), ("reject", 1)],
            "FROM workorders w\n                    JOIN events e": lambda: (_ for _ in ()).throw(
                RuntimeError("join unavailable")
            ),
            "SELECT asset_id, occurred_at\n                    FROM events": lambda: [
                ("PUMP-101", datetime(2026, 3, 13, 8, 0, tzinfo=timezone.utc)),
                ("PUMP-101", datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)),
                ("PUMP-101", datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)),
            ],
            "SELECT w.wo_id,\n                           w.workorder_created_at AS created_ts,": lambda: [
                (
                    "WO-1",
                    datetime(2026, 3, 14, 8, 0, tzinfo=timezone.utc),
                    datetime(2026, 3, 14, 14, 0, tzinfo=timezone.utc),
                    "COMPLETE",
                ),
                (
                    "WO-2",
                    datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc),
                    datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
                    "CLOSED",
                ),
            ],
            "GROUP BY w.asset_id, bucket_date": lambda: [
                ("PUMP-101", datetime(2026, 3, 14, tzinfo=timezone.utc).date(), 2)
            ],
            "GROUP BY asset_id, bucket_date": lambda: [
                ("PUMP-101", datetime(2026, 3, 14, tzinfo=timezone.utc).date(), 1, 1)
            ],
            "GROUP BY w.asset_id\n                    ORDER BY n DESC": lambda: [("PUMP-101", 4)],
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
    assert payload["mtbf_seconds_avg"] == 50400.0
    assert payload["mttr_seconds_avg"] == 16200.0
    assert payload["top_assets_by_wo_volume"] == [{"asset_id": "PUMP-101", "count": 4}]
    assert "PUMP-101" in payload["asset_metrics"]
    assert len(payload["asset_metrics"]["PUMP-101"]["workorder_volume"]) == 30
    assert any(
        point["value"] == 2 for point in payload["asset_metrics"]["PUMP-101"]["workorder_volume"]
    )
    assert len(payload["asset_metrics"]["PUMP-101"]["acceptance_rate"]) == 30
    assert any(
        point["value"] == 0.5 for point in payload["asset_metrics"]["PUMP-101"]["acceptance_rate"]
    )
    assert payload["warnings"] == ["ttr aggregation unavailable: join unavailable"]
    assert "mtbf_seconds_avg" not in payload["placeholders"]
    assert "mttr_seconds_avg" not in payload["placeholders"]
    assert fake_conn.rollback_calls == 1
    assert fake_conn.closed is True


def test_outcomes_endpoint_returns_asset_metric_daily_buckets_with_sparse_days(monkeypatch):
    fake_conn = FakeConnection(
        {
            "SELECT action, COUNT(*) FROM rca_feedback": lambda: [("accept", 3), ("reject", 1)],
            "FROM workorders w\n                    JOIN events e": lambda: [],
            "SELECT asset_id, occurred_at\n                    FROM events": lambda: [
                ("PUMP-101", datetime(2026, 3, 13, 6, 0, tzinfo=timezone.utc)),
                ("PUMP-101", datetime(2026, 3, 13, 18, 0, tzinfo=timezone.utc)),
                ("PUMP-102", datetime(2026, 3, 14, 6, 0, tzinfo=timezone.utc)),
                ("PUMP-102", datetime(2026, 3, 15, 6, 0, tzinfo=timezone.utc)),
            ],
            "SELECT w.wo_id,\n                           w.workorder_created_at AS created_ts,": lambda: [
                (
                    "WO-1",
                    datetime(2026, 3, 13, 6, 0, tzinfo=timezone.utc),
                    datetime(2026, 3, 13, 9, 0, tzinfo=timezone.utc),
                    "COMP",
                ),
                (
                    "WO-2",
                    datetime(2026, 3, 15, 7, 0, tzinfo=timezone.utc),
                    datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc),
                    "DONE",
                ),
            ],
            "GROUP BY w.asset_id, bucket_date": lambda: [
                ("PUMP-101", datetime(2026, 3, 13, tzinfo=timezone.utc).date(), 3),
                ("PUMP-102", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1),
            ],
            "GROUP BY asset_id, bucket_date": lambda: [
                ("PUMP-101", datetime(2026, 3, 13, tzinfo=timezone.utc).date(), 2, 1),
                ("PUMP-102", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 0, 1),
            ],
            "GROUP BY w.asset_id\n                    ORDER BY n DESC": lambda: [
                ("PUMP-101", 3),
                ("PUMP-102", 1),
            ],
        }
    )
    monkeypatch.setattr(outcomes_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/rca-outcomes?window=30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["mtbf_seconds_avg"] == 64800.0
    assert payload["mttr_seconds_avg"] == 11700.0
    assert sorted(payload["asset_metrics"].keys()) == ["PUMP-101", "PUMP-102"]
    assert "mtbf_seconds_avg" not in payload["placeholders"]
    assert "mttr_seconds_avg" not in payload["placeholders"]

    pump_101_volume = payload["asset_metrics"]["PUMP-101"]["workorder_volume"]
    pump_101_acceptance = payload["asset_metrics"]["PUMP-101"]["acceptance_rate"]
    assert len(pump_101_volume) == 30
    assert len(pump_101_acceptance) == 30
    assert any(point["value"] == 3 for point in pump_101_volume)
    assert any(point["value"] == 2 / 3 for point in pump_101_acceptance)
    assert any(
        point["value"] == 0 for point in payload["asset_metrics"]["PUMP-102"]["workorder_volume"]
    )
    assert any(
        point["value"] is None for point in payload["asset_metrics"]["PUMP-101"]["acceptance_rate"]
    )


def test_outcomes_endpoint_marks_partial_when_asset_trend_queries_fail(monkeypatch):
    fake_conn = FakeConnection(
        {
            "SELECT action, COUNT(*) FROM rca_feedback": lambda: [("accept", 1)],
            "FROM workorders w\n                    JOIN events e": lambda: [],
            "SELECT asset_id, occurred_at\n                    FROM events": lambda: (
                _ for _ in ()
            ).throw(RuntimeError("event interval unavailable")),
            "SELECT w.wo_id,\n                           w.workorder_created_at AS created_ts,": lambda: (
                _ for _ in ()
            ).throw(
                RuntimeError("terminal wo timestamps unavailable")
            ),
            "GROUP BY w.asset_id, bucket_date": lambda: (_ for _ in ()).throw(
                RuntimeError("wo trend unavailable")
            ),
            "GROUP BY asset_id, bucket_date": lambda: (_ for _ in ()).throw(
                RuntimeError("feedback trend unavailable")
            ),
            "GROUP BY w.asset_id\n                    ORDER BY n DESC": lambda: [],
        }
    )
    monkeypatch.setattr(outcomes_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/rca-outcomes?window=30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["asset_metrics"] == {}
    assert payload["mtbf_seconds_avg"] is None
    assert "mtbf_seconds_avg" in payload["placeholders"]
    assert payload["mttr_seconds_avg"] is None
    assert "mttr_seconds_avg" in payload["placeholders"]
    assert "mtbf aggregation unavailable: event interval unavailable" in payload["warnings"]
    assert "mttr aggregation unavailable: terminal wo timestamps unavailable" in payload["warnings"]
    assert "asset workorder trend unavailable: wo trend unavailable" in payload["warnings"]
    assert "asset acceptance trend unavailable: feedback trend unavailable" in payload["warnings"]
    assert fake_conn.rollback_calls == 4


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
            "asset_metrics": {
                "PUMP-7": {
                    "workorder_volume": [
                        {"date": "2026-03-14", "value": 2},
                        {"date": "2026-03-15", "value": 0},
                    ],
                    "acceptance_rate": [
                        {"date": "2026-03-14", "value": 0.5},
                        {"date": "2026-03-15", "value": None},
                    ],
                }
            },
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
    assert metrics["asset_PUMP-7_workorder_volume_2026-03-14"] == "2"
    assert metrics["asset_PUMP-7_workorder_volume_2026-03-15"] == "0"
    assert metrics["asset_PUMP-7_acceptance_rate_2026-03-14"] == "0.5"
    assert metrics["asset_PUMP-7_acceptance_rate_2026-03-15"] == ""
