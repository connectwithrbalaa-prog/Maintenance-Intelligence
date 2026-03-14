import datetime as dt

from maintenance_intelligence.api.outcomes import _build_ttr_measurements


def _ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_ttr_measurements_prioritize_exact_then_nearest_with_window():
    workorders = [
        {
            "wo_id": "WO-EXACT",
            "asset_id": "PUMP-101",
            "metadata": {
                "created_at": "2026-03-14T10:00:00Z",
                "resolved_at": "2026-03-14T12:00:00Z",
                "evidence_event_id": "EVT-EXACT",
            },
        },
        {
            "wo_id": "WO-NEAREST",
            "asset_id": "PUMP-102",
            "metadata": {
                "created_at": "2026-03-14T10:00:00Z",
                "resolved_at": "2026-03-14T11:00:00Z",
            },
        },
        {
            "wo_id": "WO-EXCLUDE",
            "asset_id": "PUMP-103",
            "metadata": {
                "created_at": "2026-03-14T10:00:00Z",
                "resolved_at": "2026-03-14T11:00:00Z",
            },
        },
    ]

    events = [
        {"event_id": "EVT-EXACT", "asset_id": "PUMP-101", "occurred_at": _ts("2026-03-14T09:00:00Z")},
        {"event_id": "EVT-N1", "asset_id": "PUMP-102", "occurred_at": _ts("2026-03-14T09:30:00Z")},
        {"event_id": "EVT-N2", "asset_id": "PUMP-102", "occurred_at": _ts("2026-03-14T10:45:00Z")},
        {"event_id": "EVT-FAR", "asset_id": "PUMP-103", "occurred_at": _ts("2026-03-12T10:00:00Z")},
    ]

    rows = _build_ttr_measurements(workorders, events, fallback_window_h=24)

    assert [row["wo_id"] for row in rows] == ["WO-EXACT", "WO-NEAREST"]
    assert rows[0]["event_id"] == "EVT-EXACT"
    assert rows[0]["ttr_seconds"] == 3 * 60 * 60
    assert rows[1]["event_id"] == "EVT-N2"
    assert rows[1]["ttr_seconds"] == 15 * 60


def test_ttr_measurements_do_not_fallback_when_exact_link_is_missing():
    workorders = [
        {
            "wo_id": "WO-MISSING-EXACT",
            "asset_id": "PUMP-201",
            "metadata": {
                "created_at": "2026-03-14T10:00:00Z",
                "resolved_at": "2026-03-14T11:00:00Z",
                "evidence_event_id": "EVT-NOT-FOUND",
            },
        }
    ]
    events = [
        {"event_id": "EVT-OTHER", "asset_id": "PUMP-201", "occurred_at": _ts("2026-03-14T10:30:00Z")}
    ]

    rows = _build_ttr_measurements(workorders, events, fallback_window_h=24)

    assert rows == []