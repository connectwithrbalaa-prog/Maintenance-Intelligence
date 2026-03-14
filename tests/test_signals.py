from unittest.mock import MagicMock

from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services.signals import (
    _compute_rollups,
    _detect_anomalies,
    _resolve_signal_org_id,
)


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

    _compute_rollups(mock_conn, "ORG-1", "PUMP-101", "vibration")

    # Verify queries were made
    assert mock_cur.execute.called
    # Check that insert was called
    calls = mock_cur.execute.call_args_list
    assert len(calls) >= 2  # Select and insert
    select_params = calls[0][0][1]
    insert_params = calls[1][0][1]
    assert select_params[0] == "ORG-1"
    assert insert_params[1] == "ORG-1"


def test_resolve_signal_org_id_prefers_event_then_lineage_then_default(monkeypatch):
    monkeypatch.setenv("MI_DEFAULT_ORG", "ORG-DEFAULT")
    settings = Settings()

    assert (
        _resolve_signal_org_id(
            {"org_id": "ORG-EVT", "lineage": {"org_id": "ORG-LINEAGE"}}, settings
        )
        == "ORG-EVT"
    )
    assert _resolve_signal_org_id({"lineage": {"org_id": "ORG-LINEAGE"}}, settings) == "ORG-LINEAGE"
    assert _resolve_signal_org_id({}, settings) == "ORG-DEFAULT"
