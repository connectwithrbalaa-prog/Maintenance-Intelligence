from datetime import datetime, timezone

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import reports as reports_mod


READ_HEADERS = {"x-user-id": "viewer-1", "x-user-role": "viewer"}


class FakePrioritizedCursor:
    def __init__(self):
        self.rows = []

    def execute(self, sql):
        normalized = " ".join(sql.split())
        if "SELECT asset_id, COUNT(*) AS ev_count, MAX(occurred_at) AS last_evt_at FROM events" in normalized:
            self.rows = [
                ("PUMP-101", 3, datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)),
                ("PUMP-202", 2, datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc)),
            ]
            return
        if "SELECT DISTINCT ON (asset_id) asset_id, severity, occurred_at FROM events" in normalized:
            self.rows = [
                ("PUMP-101", "high", datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)),
                ("PUMP-202", "medium", datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc)),
            ]
            return
        if "SELECT asset_id, COUNT(*) AS wo_count, SUM(CASE WHEN UPPER(COALESCE(status, '')) IN ('COMP', 'COMPLETE', 'COMPLETED', 'CLOSE', 'CLOSED', 'DONE') THEN 0 ELSE 1 END) AS open_wo_count FROM workorders" in normalized:
            self.rows = [
                ("PUMP-101", 1, 0),
                ("PUMP-202", 2, 2),
                ("FAN-9", 4, 4),
            ]
            return
        if "SELECT asset_id, SUM(CASE WHEN action = 'accept' THEN 1 ELSE 0 END) AS accept_count, SUM(CASE WHEN action = 'reject' THEN 1 ELSE 0 END) AS reject_count FROM rca_feedback" in normalized:
            self.rows = [
                ("PUMP-101", 2, 0),
                ("PUMP-202", 0, 1),
                ("FAN-9", 0, 1),
            ]
            return
        if "SELECT asset_id, signal_type, period, end_time, mean, max, anomaly_flags FROM signal_rollups" in normalized:
            self.rows = [
                ("PUMP-101", "vibration", "24h", datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc), 7.8, 8.1, {"high_vibration": True}),
                ("PUMP-202", "temperature", "1h", datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc), 91.0, 94.0, {"high_temperature": True, "z_score_spike": True}),
            ]
            return
        if "SELECT asset_id, severity, occurred_at, details FROM events" in normalized:
            self.rows = [
                ("PUMP-101", "high", datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc), {"rms": 8.1, "threshold": 9.0}),
                ("PUMP-101", "high", datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc), {"rms": 7.9, "threshold": 9.0}),
                ("PUMP-101", "high", datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc), {"rms": 8.0, "threshold": 9.0}),
                ("PUMP-202", "medium", datetime(2026, 3, 15, 7, 0, tzinfo=timezone.utc), {"temperature": 92.0, "threshold": 90.0}),
                ("PUMP-202", "medium", datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc), {"temperature": 93.0, "threshold": 90.0}),
            ]
            return
        if "SELECT asset_id, occurred_at FROM events" in normalized:
            self.rows = [
                ("PUMP-101", datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)),
                ("PUMP-101", datetime(2026, 3, 12, 8, 0, tzinfo=timezone.utc)),
                ("PUMP-101", datetime(2026, 3, 15, 8, 0, tzinfo=timezone.utc)),
                ("PUMP-202", datetime(2026, 3, 15, 7, 0, tzinfo=timezone.utc)),
                ("PUMP-202", datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc)),
            ]
            return
        raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePrioritizedConnection:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return FakePrioritizedCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        self.closed = True


def test_prioritized_assets_requires_authenticated_identity(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    client = TestClient(app)

    response = client.get("/api/v1/reports/prioritized-assets?limit=5")

    assert response.status_code == 403
    assert response.json()["detail"] == "Prioritized asset reports require an authenticated identity"


def test_prioritized_assets_ranks_assets_by_signal_feedback_and_mtbf_risk(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_conn = FakePrioritizedConnection()
    monkeypatch.setattr(reports_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/prioritized-assets?limit=5&window=30", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert [row["asset_id"] for row in payload] == ["PUMP-202", "PUMP-101", "FAN-9"]

    highest = payload[0]
    assert highest["asset_id"] == "PUMP-202"
    assert highest["latest_severity"] == "medium"
    assert highest["events_window"] == 2
    assert highest["workorders_window"] == 2
    assert highest["open_workorders"] == 2
    assert highest["signal_anomaly_score"] == 6.0
    assert highest["feedback_acceptance_rate"] == 0.0
    assert highest["mtbf_seconds"] == 14400.0
    assert highest["early_warning_status"] == "elevated"
    assert highest["early_warning_score"] == 66.0
    assert highest["early_warning_reasons"] == [
        "Signal rollups still carry anomaly flags",
        "Temperature remains at 94.0 C",
    ]
    assert highest["score_components"]["feedback_risk"] == 4.0
    assert highest["score_components"]["mtbf_risk"] == 6.0
    assert highest["score_components"]["signal_risk"] == 18.0

    second = payload[1]
    assert second["asset_id"] == "PUMP-101"
    assert second["latest_severity"] == "high"
    assert second["signal_anomaly_score"] == 1.0
    assert second["feedback_acceptance_rate"] == 1.0
    assert second["mtbf_seconds"] == 216000.0
    assert second["early_warning_status"] == "elevated"
    assert second["early_warning_score"] == 51.0
    assert second["early_warning_reasons"] == [
        "High-severity events have repeated for this asset",
        "Signal rollups still carry anomaly flags",
        "Vibration is trending high at 8.1 mm/s",
    ]
    assert second["last_event_at"] == "2026-03-15T10:00:00Z"
    assert second["score_components"]["feedback_risk"] == 0.0

    third = payload[2]
    assert third["asset_id"] == "FAN-9"
    assert third["priority_score"] > second["priority_score"]
    assert third["early_warning_status"] is None
    assert third["early_warning_reasons"] == []

    assert fake_conn.closed is True


def test_prioritized_assets_filters_to_warning_status_assets(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    fake_conn = FakePrioritizedConnection()
    monkeypatch.setattr(reports_mod, "with_pg", lambda _dsn: fake_conn)

    client = TestClient(app)
    response = client.get("/api/v1/reports/prioritized-assets?limit=5&window=30&warnings_only=true", headers=READ_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert [row["asset_id"] for row in payload] == ["PUMP-202", "PUMP-101"]
    assert all(row["early_warning_status"] in {"critical", "elevated", "watch"} for row in payload)