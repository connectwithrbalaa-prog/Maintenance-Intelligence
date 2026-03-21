import csv
import io
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import outcomes as outcomes_mod
from maintenance_intelligence.api import reports as reports_mod

READ_HEADERS = {"x-user-id": "viewer-1", "x-user-role": "viewer"}


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
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(
        outcomes_mod,
        "build_early_warning_report",
        lambda event_rows, rollup_rows: {
            "summary": {
                "total_assets": 2,
                "status_counts": {"critical": 1, "elevated": 1, "watch": 0, "normal": 0},
                "top_assets": [
                    {
                        "asset_id": "PUMP-202",
                        "score": 78.0,
                        "status": "critical",
                        "reasons": ["Temperature remains high"],
                    }
                ],
                "last_evaluated_at": "2026-03-15T12:00:00Z",
            },
            "asset_metrics": {
                "PUMP-101": {
                    "early_warning_score": 52.0,
                    "early_warning_status": "elevated",
                    "early_warning_reasons": ["Signal rollups still carry anomaly flags"],
                },
                "PUMP-202": {
                    "early_warning_score": 78.0,
                    "early_warning_status": "critical",
                    "early_warning_reasons": ["Temperature remains at 91.0 C"],
                },
            },
        },
    )
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
            "SELECT asset_id, severity, occurred_at, details": lambda: [],
            "SELECT asset_id,\n                           signal_type,": lambda: [],
            "GROUP BY w.asset_id\n                    ORDER BY n DESC": lambda: [("PUMP-101", 4)],
            "LEFT JOIN workorders w ON w.wo_id = p.work_order_id": lambda: [
                (
                    "REC-44",
                    "approved",
                    "WO-1",
                    {
                        "approval": {
                            "handoff_state": "success",
                            "approved_at": "2026-03-14T09:55:00Z",
                        },
                        "approval_attempts": [
                            {"attempted_at": "2026-03-14T09:55:00Z", "handoff_state": "success"}
                        ],
                    },
                    datetime(2026, 3, 14, 10, 5, tzinfo=timezone.utc),
                    "PUMP-101",
                    "PUMP-101",
                    {"handoff": {"backend": "maximo"}},
                    datetime(2026, 3, 14, 9, 55, tzinfo=timezone.utc),
                ),
                (
                    "REC-21",
                    "pending",
                    None,
                    {
                        "approval": {
                            "handoff_state": "failure",
                            "attempted_at": "2026-03-14T08:05:00Z",
                        },
                        "approval_attempts": [
                            {"attempted_at": "2026-03-14T08:05:00Z", "handoff_state": "failure"}
                        ],
                    },
                    None,
                    "PUMP-202",
                    None,
                    {},
                    datetime(2026, 3, 14, 8, 5, tzinfo=timezone.utc),
                ),
                (
                    "REC-77",
                    "pending",
                    None,
                    {
                        "approval": {
                            "handoff_state": "failure",
                            "attempted_at": "2026-03-15T08:05:00Z",
                        },
                        "approval_attempts": [
                            {"attempted_at": "2026-03-15T07:05:00Z", "handoff_state": "pending"},
                            {"attempted_at": "2026-03-15T07:35:00Z", "handoff_state": "failure"},
                            {"attempted_at": "2026-03-15T08:05:00Z", "handoff_state": "failure"},
                        ],
                    },
                    None,
                    "PUMP-202",
                    None,
                    {},
                    datetime(2026, 3, 15, 8, 5, tzinfo=timezone.utc),
                ),
                (
                    "REC-55",
                    "pending",
                    None,
                    {
                        "approval": {
                            "handoff_state": "pending",
                            "attempted_at": "2026-03-15T11:05:00Z",
                        },
                        "approval_attempts": [
                            {"attempted_at": "2026-03-15T11:05:00Z", "handoff_state": "pending"}
                        ],
                    },
                    None,
                    "PUMP-303",
                    None,
                    {},
                    datetime(2026, 3, 15, 11, 5, tzinfo=timezone.utc),
                ),
            ],
            "SELECT user_id AS entity_id, action, COUNT(*) AS n": lambda: [
                ("operator-1", "accept", 1),
                ("operator-2", "reject", 1),
                ("operator-3", "accept", 1),
            ],
            "SELECT user_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               COUNT(*) AS n": lambda: [
                ("operator-1", datetime(2026, 3, 14, tzinfo=timezone.utc).date(), 1),
                ("operator-2", datetime(2026, 3, 14, tzinfo=timezone.utc).date(), 1),
                ("operator-3", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1),
            ],
            "SELECT user_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accepted_count": lambda: [
                ("operator-1", datetime(2026, 3, 14, tzinfo=timezone.utc).date(), 1, 0),
                ("operator-2", datetime(2026, 3, 14, tzinfo=timezone.utc).date(), 0, 1),
                ("operator-3", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1, 0),
            ],
            "SELECT user_id AS entity_id, COUNT(*) AS n": lambda: [
                ("operator-1", 1),
                ("operator-2", 1),
                ("operator-3", 1),
            ],
            "SELECT org_id AS entity_id, action, COUNT(*) AS n": lambda: [
                ("demo-org", "accept", 2),
                ("demo-org", "reject", 1),
            ],
            "SELECT org_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               COUNT(*) AS n": lambda: [
                ("demo-org", datetime(2026, 3, 14, tzinfo=timezone.utc).date(), 2),
                ("demo-org", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1),
            ],
            "SELECT org_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accepted_count": lambda: [
                ("demo-org", datetime(2026, 3, 14, tzinfo=timezone.utc).date(), 1, 1),
                ("demo-org", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1, 0),
            ],
            "SELECT org_id AS entity_id, COUNT(*) AS n": lambda: [("demo-org", 3)],
        }
    )
    monkeypatch.setattr(outcomes_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/rca-outcomes?window=30", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["window_days"] == 30
    assert payload["feedback_counts"] == {"accept": 2, "reject": 1, "edited": 0}
    assert payload["feedback_total"] == 3
    assert payload["acceptance_rate"] == 2 / 3
    assert payload["early_warning_summary"]["status_counts"] == {
        "critical": 1,
        "elevated": 1,
        "watch": 0,
        "normal": 0,
    }
    assert payload["early_warning_summary"]["top_assets"][0]["asset_id"] == "PUMP-202"
    assert payload["ttr_seconds_avg"] is None
    assert payload["mtbf_seconds_avg"] == 50400.0
    assert payload["mttr_seconds_avg"] == 16200.0
    assert payload["top_assets_by_wo_volume"] == [{"asset_id": "PUMP-101", "count": 4}]
    assert payload["asset_metrics"]["PUMP-101"]["early_warning_status"] == "elevated"
    assert payload["asset_metrics"]["PUMP-202"]["early_warning_score"] == 78.0
    assert payload["cmms_summary"] == {
        "success_total": 1,
        "pending_total": 1,
        "failure_total": 2,
        "admin_retry_required_total": 3,
        "limit_reached_total": 1,
        "approval_to_handoff_seconds_avg": 600.0,
    }
    assert payload["cmms_breakdowns"] == {
        "by_asset": {
            "PUMP-101": {
                "success_total": 1,
                "pending_total": 0,
                "failure_total": 0,
                "admin_retry_required_total": 0,
                "limit_reached_total": 0,
                "approval_to_handoff_seconds_avg": 600.0,
            },
            "PUMP-202": {
                "success_total": 0,
                "pending_total": 0,
                "failure_total": 2,
                "admin_retry_required_total": 2,
                "limit_reached_total": 1,
                "approval_to_handoff_seconds_avg": None,
            },
            "PUMP-303": {
                "success_total": 0,
                "pending_total": 1,
                "failure_total": 0,
                "admin_retry_required_total": 1,
                "limit_reached_total": 0,
                "approval_to_handoff_seconds_avg": None,
            },
        },
        "by_backend": {
            "maximo": {
                "success_total": 1,
                "pending_total": 0,
                "failure_total": 0,
                "admin_retry_required_total": 0,
                "limit_reached_total": 0,
                "approval_to_handoff_seconds_avg": 600.0,
            },
            "unknown": {
                "success_total": 0,
                "pending_total": 1,
                "failure_total": 2,
                "admin_retry_required_total": 3,
                "limit_reached_total": 1,
                "approval_to_handoff_seconds_avg": None,
            },
        },
    }
    assert payload["top_users_by_feedback"] == [
        {"user_id": "operator-1", "count": 1},
        {"user_id": "operator-2", "count": 1},
        {"user_id": "operator-3", "count": 1},
    ]
    assert payload["top_orgs_by_feedback"] == [{"org_id": "demo-org", "count": 3}]
    assert "PUMP-101" in payload["asset_metrics"]
    assert payload["top_backends_by_handoff_volume"] == [
        {"backend": "unknown", "count": 3},
        {"backend": "maximo", "count": 1},
    ]
    assert sorted(payload["backend_metrics"].keys()) == ["maximo", "unknown"]
    assert payload["backend_metrics"]["maximo"]["handoff_total"] == 1
    assert payload["backend_metrics"]["maximo"]["handoff_success_rate"] == 1.0
    assert payload["backend_metrics"]["unknown"]["handoff_total"] == 3
    assert payload["backend_metrics"]["unknown"]["handoff_success_rate"] == 0.0
    assert any(
        point["value"] == 2 for point in payload["backend_metrics"]["unknown"]["handoff_volume"]
    )
    assert any(
        point["value"] == 0.0
        for point in payload["backend_metrics"]["unknown"]["handoff_success_rate_series"]
        if point["value"] is not None
    )
    assert payload["user_metrics"]["operator-1"]["feedback_counts"] == {
        "accept": 1,
        "reject": 0,
        "edited": 0,
    }
    assert payload["user_metrics"]["operator-1"]["feedback_total"] == 1
    assert payload["user_metrics"]["operator-1"]["acceptance_rate"] == 1.0
    assert len(payload["user_metrics"]["operator-1"]["feedback_volume"]) == 30
    assert any(
        point["value"] == 1 for point in payload["user_metrics"]["operator-1"]["feedback_volume"]
    )
    assert any(
        point["value"] == 1.0
        for point in payload["user_metrics"]["operator-1"]["acceptance_rate_series"]
        if point["value"] is not None
    )
    assert payload["org_metrics"]["demo-org"]["feedback_counts"] == {
        "accept": 2,
        "reject": 1,
        "edited": 0,
    }
    assert payload["org_metrics"]["demo-org"]["feedback_total"] == 3
    assert payload["org_metrics"]["demo-org"]["acceptance_rate"] == 2 / 3
    assert len(payload["org_metrics"]["demo-org"]["feedback_volume"]) == 30
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
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(
        outcomes_mod,
        "build_early_warning_report",
        lambda event_rows, rollup_rows: {
            "summary": {
                "total_assets": 2,
                "status_counts": {"critical": 0, "elevated": 1, "watch": 1, "normal": 0},
                "top_assets": [
                    {
                        "asset_id": "PUMP-102",
                        "score": 61.0,
                        "status": "elevated",
                        "reasons": ["A fresh event landed within the last 24 hours"],
                    }
                ],
                "last_evaluated_at": "2026-03-15T10:00:00Z",
            },
            "asset_metrics": {
                "PUMP-101": {
                    "early_warning_score": 28.0,
                    "early_warning_status": "watch",
                    "early_warning_reasons": [
                        "Low-volume warning signals are present but not yet persistent"
                    ],
                },
                "PUMP-102": {
                    "early_warning_score": 61.0,
                    "early_warning_status": "elevated",
                    "early_warning_reasons": ["A fresh event landed within the last 24 hours"],
                },
            },
        },
    )
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
            "SELECT asset_id, severity, occurred_at, details": lambda: [],
            "SELECT asset_id,\n                           signal_type,": lambda: [],
            "GROUP BY w.asset_id\n                    ORDER BY n DESC": lambda: [
                ("PUMP-101", 3),
                ("PUMP-102", 1),
            ],
            "LEFT JOIN workorders w ON w.wo_id = p.work_order_id": lambda: [
                (
                    "REC-44",
                    "approved",
                    "WO-1",
                    {
                        "approval": {
                            "handoff_state": "success",
                            "approved_at": "2026-03-13T05:50:00Z",
                        },
                        "approval_attempts": [
                            {"attempted_at": "2026-03-13T05:50:00Z", "handoff_state": "success"}
                        ],
                    },
                    datetime(2026, 3, 13, 6, 0, tzinfo=timezone.utc),
                    "PUMP-101",
                    "PUMP-101",
                    {"handoff": {"backend": "maximo"}},
                ),
                (
                    "REC-45",
                    "approved",
                    "WO-2",
                    {
                        "approval": {
                            "handoff_state": "success",
                            "approved_at": "2026-03-15T06:52:00Z",
                        },
                        "approval_attempts": [
                            {"attempted_at": "2026-03-15T06:52:00Z", "handoff_state": "success"}
                        ],
                    },
                    datetime(2026, 3, 15, 7, 0, tzinfo=timezone.utc),
                    "PUMP-102",
                    "PUMP-102",
                    {"handoff": {"backend": "mock"}},
                ),
                (
                    "REC-46",
                    "pending",
                    None,
                    {
                        "approval": {
                            "handoff_state": "pending",
                            "attempted_at": "2026-03-15T06:40:00Z",
                        }
                    },
                    None,
                    "PUMP-102",
                    None,
                    {},
                ),
            ],
            "SELECT user_id AS entity_id, action, COUNT(*) AS n": lambda: [
                ("operator-1", "accept", 2),
                ("operator-2", "reject", 1),
                ("operator-3", "accept", 1),
            ],
            "SELECT user_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               COUNT(*) AS n": lambda: [
                ("operator-1", datetime(2026, 3, 13, tzinfo=timezone.utc).date(), 2),
                ("operator-2", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1),
                ("operator-3", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1),
            ],
            "SELECT user_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accepted_count": lambda: [
                ("operator-1", datetime(2026, 3, 13, tzinfo=timezone.utc).date(), 2, 0),
                ("operator-2", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 0, 1),
                ("operator-3", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1, 0),
            ],
            "SELECT user_id AS entity_id, COUNT(*) AS n": lambda: [
                ("operator-1", 2),
                ("operator-2", 1),
                ("operator-3", 1),
            ],
            "SELECT org_id AS entity_id, action, COUNT(*) AS n": lambda: [
                ("demo-org", "accept", 3),
                ("demo-org", "reject", 1),
            ],
            "SELECT org_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               COUNT(*) AS n": lambda: [
                ("demo-org", datetime(2026, 3, 13, tzinfo=timezone.utc).date(), 3),
                ("demo-org", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1),
            ],
            "SELECT org_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accepted_count": lambda: [
                ("demo-org", datetime(2026, 3, 13, tzinfo=timezone.utc).date(), 2, 1),
                ("demo-org", datetime(2026, 3, 15, tzinfo=timezone.utc).date(), 1, 0),
            ],
            "SELECT org_id AS entity_id, COUNT(*) AS n": lambda: [("demo-org", 4)],
        }
    )
    monkeypatch.setattr(outcomes_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/rca-outcomes?window=30", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["early_warning_summary"]["status_counts"] == {
        "critical": 0,
        "elevated": 1,
        "watch": 1,
        "normal": 0,
    }
    assert payload["asset_metrics"]["PUMP-101"]["early_warning_status"] == "watch"
    assert payload["asset_metrics"]["PUMP-102"]["early_warning_score"] == 61.0
    assert payload["mtbf_seconds_avg"] == 64800.0
    assert payload["mttr_seconds_avg"] == 11700.0
    assert sorted(payload["asset_metrics"].keys()) == ["PUMP-101", "PUMP-102"]
    assert sorted(payload["user_metrics"].keys()) == ["operator-1", "operator-2", "operator-3"]
    assert sorted(payload["org_metrics"].keys()) == ["demo-org"]
    assert payload["cmms_summary"] == {
        "success_total": 2,
        "pending_total": 1,
        "failure_total": 0,
        "admin_retry_required_total": 1,
        "limit_reached_total": 0,
        "approval_to_handoff_seconds_avg": 540.0,
    }
    assert payload["cmms_breakdowns"] == {
        "by_asset": {
            "PUMP-101": {
                "success_total": 1,
                "pending_total": 0,
                "failure_total": 0,
                "admin_retry_required_total": 0,
                "limit_reached_total": 0,
                "approval_to_handoff_seconds_avg": 600.0,
            },
            "PUMP-102": {
                "success_total": 1,
                "pending_total": 1,
                "failure_total": 0,
                "admin_retry_required_total": 1,
                "limit_reached_total": 0,
                "approval_to_handoff_seconds_avg": 480.0,
            },
        },
        "by_backend": {
            "maximo": {
                "success_total": 1,
                "pending_total": 0,
                "failure_total": 0,
                "admin_retry_required_total": 0,
                "limit_reached_total": 0,
                "approval_to_handoff_seconds_avg": 600.0,
            },
            "mock": {
                "success_total": 1,
                "pending_total": 0,
                "failure_total": 0,
                "admin_retry_required_total": 0,
                "limit_reached_total": 0,
                "approval_to_handoff_seconds_avg": 480.0,
            },
            "unknown": {
                "success_total": 0,
                "pending_total": 1,
                "failure_total": 0,
                "admin_retry_required_total": 1,
                "limit_reached_total": 0,
                "approval_to_handoff_seconds_avg": None,
            },
        },
    }
    assert payload["top_users_by_feedback"][0] == {"user_id": "operator-1", "count": 2}
    assert payload["top_orgs_by_feedback"] == [{"org_id": "demo-org", "count": 4}]
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
    assert payload["user_metrics"]["operator-2"]["acceptance_rate"] == 0.0
    assert any(
        point["value"] == 2 for point in payload["user_metrics"]["operator-1"]["feedback_volume"]
    )
    assert any(
        point["value"] == 1.0
        for point in payload["user_metrics"]["operator-1"]["acceptance_rate_series"]
        if point["value"] is not None
    )
    assert payload["org_metrics"]["demo-org"]["acceptance_rate"] == 3 / 4


def test_outcomes_endpoint_marks_partial_when_asset_trend_queries_fail(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
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
            "SELECT asset_id, severity, occurred_at, details": lambda: (_ for _ in ()).throw(
                RuntimeError("event warning input unavailable")
            ),
            "SELECT asset_id,\n                           signal_type,": lambda: (
                _ for _ in ()
            ).throw(RuntimeError("signal warning input unavailable")),
            "GROUP BY w.asset_id\n                    ORDER BY n DESC": lambda: [],
            "LEFT JOIN workorders w ON w.wo_id = p.work_order_id": lambda: (_ for _ in ()).throw(
                RuntimeError("proposal summary unavailable")
            ),
            "SELECT user_id AS entity_id, action, COUNT(*) AS n": lambda: [],
            "SELECT user_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               COUNT(*) AS n": lambda: [],
            "SELECT user_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accepted_count": lambda: [],
            "SELECT user_id AS entity_id, COUNT(*) AS n": lambda: [],
            "SELECT org_id AS entity_id, action, COUNT(*) AS n": lambda: [],
            "SELECT org_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               COUNT(*) AS n": lambda: [],
            "SELECT org_id AS entity_id,\n                               DATE_TRUNC('day', created_at)::date AS bucket_date,\n                               SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accepted_count": lambda: [],
            "SELECT org_id AS entity_id, COUNT(*) AS n": lambda: [],
        }
    )
    monkeypatch.setattr(outcomes_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/rca-outcomes?window=30", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["asset_metrics"] == {}
    assert payload["backend_metrics"] == {}
    assert payload["user_metrics"] == {}
    assert payload["org_metrics"] == {}
    assert payload["early_warning_summary"]["top_assets"] == []
    assert payload["cmms_summary"] == {
        "success_total": 0,
        "pending_total": 0,
        "failure_total": 0,
        "admin_retry_required_total": 0,
        "limit_reached_total": 0,
        "approval_to_handoff_seconds_avg": None,
    }
    assert payload["cmms_breakdowns"] == {"by_asset": {}, "by_backend": {}}
    assert payload["mtbf_seconds_avg"] is None
    assert "mtbf_seconds_avg" in payload["placeholders"]
    assert payload["mttr_seconds_avg"] is None
    assert "mttr_seconds_avg" in payload["placeholders"]
    assert "mtbf aggregation unavailable: event interval unavailable" in payload["warnings"]
    assert "mttr aggregation unavailable: terminal wo timestamps unavailable" in payload["warnings"]
    assert "asset workorder trend unavailable: wo trend unavailable" in payload["warnings"]
    assert "asset acceptance trend unavailable: feedback trend unavailable" in payload["warnings"]
    assert (
        "early warning summary unavailable: event warning input unavailable" in payload["warnings"]
    )
    assert "cmms handoff summary unavailable: proposal summary unavailable" in payload["warnings"]
    assert fake_conn.rollback_calls == 6


def test_outcomes_endpoints_require_authenticated_identity(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    client = TestClient(app)

    report_response = client.get("/api/v1/reports/rca-outcomes?window=30")
    csv_response = client.get("/api/v1/reports/rca-outcomes/csv?window=30")

    assert report_response.status_code == 403
    assert report_response.json()["detail"] == "Outcomes reports require an authenticated identity"
    assert csv_response.status_code == 403
    assert csv_response.json()["detail"] == "Outcomes reports require an authenticated identity"


def test_outcomes_csv_includes_stable_placeholder_rows(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    monkeypatch.setattr(
        outcomes_mod,
        "rca_outcomes",
        lambda request, window=30: {
            "window_days": window,
            "status": "partial",
            "warnings": ["missing lifecycle timestamps"],
            "early_warning_summary": {
                "total_assets": 1,
                "status_counts": {"critical": 0, "elevated": 1, "watch": 0, "normal": 0},
                "top_assets": [{"asset_id": "PUMP-7", "score": 63.0, "status": "elevated"}],
                "last_evaluated_at": "2026-03-15T12:00:00Z",
            },
            "feedback_counts": {"accept": 1, "reject": 0, "edited": 2},
            "feedback_total": 3,
            "acceptance_rate": 1 / 3,
            "ttr_seconds_avg": None,
            "mtbf_seconds_avg": None,
            "mttr_seconds_avg": None,
            "cmms_summary": {
                "success_total": 2,
                "pending_total": 1,
                "failure_total": 1,
                "admin_retry_required_total": 2,
                "limit_reached_total": 1,
                "approval_to_handoff_seconds_avg": 450.0,
            },
            "cmms_breakdowns": {
                "by_asset": {
                    "PUMP-7": {
                        "success_total": 2,
                        "pending_total": 1,
                        "failure_total": 1,
                        "admin_retry_required_total": 2,
                        "limit_reached_total": 1,
                        "approval_to_handoff_seconds_avg": 450.0,
                    }
                },
                "by_backend": {
                    "maximo": {
                        "success_total": 1,
                        "pending_total": 1,
                        "failure_total": 0,
                        "admin_retry_required_total": 1,
                        "limit_reached_total": 0,
                        "approval_to_handoff_seconds_avg": 300.0,
                    },
                    "mock": {
                        "success_total": 1,
                        "pending_total": 0,
                        "failure_total": 1,
                        "admin_retry_required_total": 1,
                        "limit_reached_total": 1,
                        "approval_to_handoff_seconds_avg": 600.0,
                    },
                },
            },
            "top_assets_by_wo_volume": [{"asset_id": "PUMP-7", "count": 2}],
            "top_backends_by_handoff_volume": [{"backend": "maximo", "count": 2}],
            "top_users_by_feedback": [{"user_id": "operator-9", "count": 2}],
            "top_orgs_by_feedback": [{"org_id": "demo-org", "count": 3}],
            "asset_metrics": {
                "PUMP-7": {
                    "early_warning_score": 63.0,
                    "early_warning_status": "elevated",
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
            "backend_metrics": {
                "maximo": {
                    "handoff_total": 2,
                    "handoff_success_rate": 0.5,
                    "handoff_volume": [
                        {"date": "2026-03-14", "value": 1},
                        {"date": "2026-03-15", "value": 1},
                    ],
                    "handoff_success_rate_series": [
                        {"date": "2026-03-14", "value": 1.0},
                        {"date": "2026-03-15", "value": 0.0},
                    ],
                }
            },
            "user_metrics": {
                "operator-9": {
                    "feedback_counts": {"accept": 1, "reject": 0, "edited": 1},
                    "feedback_total": 2,
                    "acceptance_rate": 1.0,
                    "feedback_volume": [
                        {"date": "2026-03-14", "value": 2},
                        {"date": "2026-03-15", "value": 0},
                    ],
                    "acceptance_rate_series": [
                        {"date": "2026-03-14", "value": 1.0},
                        {"date": "2026-03-15", "value": None},
                    ],
                }
            },
            "org_metrics": {
                "demo-org": {
                    "feedback_counts": {"accept": 1, "reject": 0, "edited": 2},
                    "feedback_total": 3,
                    "acceptance_rate": 1.0,
                    "feedback_volume": [
                        {"date": "2026-03-14", "value": 2},
                        {"date": "2026-03-15", "value": 1},
                    ],
                    "acceptance_rate_series": [
                        {"date": "2026-03-14", "value": 1.0},
                        {"date": "2026-03-15", "value": None},
                    ],
                }
            },
            "placeholders": {},
        },
    )

    client = TestClient(app)
    response = client.get("/api/v1/reports/rca-outcomes/csv?window=30", headers=READ_HEADERS)

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
    assert metrics["early_warning_total_assets"] == "1"
    assert metrics["early_warning_elevated_total"] == "1"
    assert metrics["early_warning_top_asset_PUMP-7_score"] == "63.0"
    assert metrics["asset_PUMP-7_early_warning_score"] == "63.0"
    assert metrics["asset_PUMP-7_early_warning_status"] == "elevated"
    assert metrics["cmms_success_total"] == "2"
    assert metrics["cmms_pending_total"] == "1"
    assert metrics["cmms_failure_total"] == "1"
    assert metrics["cmms_admin_retry_required_total"] == "2"
    assert metrics["cmms_limit_reached_total"] == "1"
    assert metrics["cmms_approval_to_handoff_seconds_avg"] == "450.0"
    assert metrics["cmms_asset_PUMP-7_success_total"] == "2"
    assert metrics["cmms_asset_PUMP-7_approval_to_handoff_seconds_avg"] == "450.0"
    assert metrics["cmms_backend_maximo_pending_total"] == "1"
    assert metrics["cmms_backend_mock_limit_reached_total"] == "1"
    assert metrics["top_asset_PUMP-7_wo_count"] == "2"
    assert metrics["top_backend_maximo_handoff_count"] == "2"
    assert metrics["asset_PUMP-7_workorder_volume_2026-03-14"] == "2"
    assert metrics["asset_PUMP-7_workorder_volume_2026-03-15"] == "0"
    assert metrics["asset_PUMP-7_acceptance_rate_2026-03-14"] == "0.5"
    assert metrics["asset_PUMP-7_acceptance_rate_2026-03-15"] == ""
    assert metrics["backend_maximo_handoff_total"] == "2"
    assert metrics["backend_maximo_handoff_success_rate"] == "0.5"
    assert metrics["backend_maximo_handoff_volume_2026-03-14"] == "1"
    assert metrics["backend_maximo_handoff_success_rate_2026-03-15"] == "0.0"
    assert metrics["user_operator-9_feedback_accept"] == "1"
    assert metrics["user_operator-9_feedback_edited"] == "1"
    assert metrics["user_operator-9_feedback_total"] == "2"
    assert metrics["user_operator-9_feedback_volume_2026-03-14"] == "2"
    assert metrics["user_operator-9_acceptance_rate_2026-03-14"] == "1.0"


class _BadActorCursor:
    def __init__(self):
        self.rows = []

    def execute(self, sql):
        normalized = " ".join(sql.split())
        if "SELECT asset_id, COUNT(*) AS ev_count" in normalized:
            self.rows = [("PUMP-101", 4, datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc))]
            return
        if "SELECT DISTINCT ON (asset_id)" in normalized:
            self.rows = [("PUMP-101", "high", datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc))]
            return
        if "SELECT asset_id, COUNT(*) AS wo_count" in normalized:
            self.rows = [("PUMP-101", 2)]
            return
        raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _BadActorConnection:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return _BadActorCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self.closed = True


def test_bad_actor_report_requires_authenticated_identity(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    client = TestClient(app)

    response = client.get("/api/v1/reports/bad-actors?limit=5")

    assert response.status_code == 403
    assert response.json()["detail"] == "Bad-actor reports require an authenticated identity"


def test_bad_actor_report_returns_ranked_assets_for_authenticated_reads(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_conn = _BadActorConnection()
    monkeypatch.setattr(reports_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/bad-actors?limit=5", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "asset_id": "PUMP-101",
            "score": 8,
            "events_90d": 4,
            "workorders_90d": 2,
            "latest_severity": "high",
            "last_event_at": "2026-03-15T10:00:00Z",
        }
    ]
    assert fake_conn.closed is True
