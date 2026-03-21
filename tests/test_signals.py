from maintenance_intelligence.services.signals import _detect_anomalies, _compute_rollups
from unittest.mock import MagicMock


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
