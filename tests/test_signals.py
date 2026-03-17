import pytest
from maintenance_intelligence.services.signals import _detect_anomalies, _compute_rollups
import psycopg2
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import signals as signals_mod

def test_detect_anomalies():
    # Normal values
    recent = [1.0, 1.1, 0.9, 1.0, 1.2]
    assert _detect_anomalies(recent, 1.0) == {}

    # Threshold exceeded
    assert _detect_anomalies(recent, 2.5, threshold=1.0) == {"threshold_exceeded": True}

    # Z-score spike
    recent = [1.0] * 10 + [10.0]  # Mean ~1.8, stdev ~2.8, z-score > 3
    anomalies = _detect_anomalies(recent, 10.0)
    assert "z_score_spike" in anomalies

def test_compute_rollups():
    # Mock connection and cursor
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock()

    # Mock signal data
    mock_cur.fetchall.return_value = [{"value": 1.0}, {"value": 2.0}, {"value": 3.0}]

    _compute_rollups(mock_conn, "PUMP-101", "vibration")

    # Verify queries were made
    assert mock_cur.execute.called
    # Check that insert was called
    calls = mock_cur.execute.call_args_list
    assert len(calls) >= 2  # Select and insert


def test_signals_summary_requires_authenticated_identity(monkeypatch):
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)
    client = TestClient(app)

    response = client.get("/api/v1/signals/summary?asset_id=PUMP-101&limit=2")

    assert response.status_code == 403
    assert response.json()["detail"] == "Signal summaries require an authenticated identity"


def test_signals_summary_returns_recent_signals_for_authenticated_reads(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock()
    mock_cur.fetchall.side_effect = [
        [
            ("SIG-1", "vibration", 4.2, "mm/s", None, {"source": "sensor-a"}),
        ],
        [
            ("vibration", "1h", 4.0, 3.5, 4.8, {"threshold_exceeded": True}, None),
        ],
    ]
    monkeypatch.setattr(signals_mod, "with_pg", lambda _dsn: mock_conn)

    client = TestClient(app)
    response = client.get(
        "/api/v1/signals/summary?asset_id=PUMP-101&limit=2",
        headers={"x-user-id": "viewer-1", "x-user-role": "viewer"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "asset_id": "PUMP-101",
        "recent_signals": [
            {
                "signal_id": "SIG-1",
                "signal_type": "vibration",
                "value": 4.2,
                "unit": "mm/s",
                "timestamp": None,
                "metadata": {"source": "sensor-a"},
            }
        ],
        "rollups": [
            {
                "signal_type": "vibration",
                "period": "1h",
                "mean": 4.0,
                "min": 3.5,
                "max": 4.8,
                "anomalies": {"threshold_exceeded": True},
                "end_time": None,
            }
        ],
    }