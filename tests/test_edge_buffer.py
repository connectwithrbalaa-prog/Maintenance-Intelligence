from maintenance_intelligence.runner.edge_agent import EdgeEventBuffer


def _event(event_id: str) -> dict:
    return {
        "event_id": event_id,
        "occurred_at": "2026-03-15T10:00:00Z",
        "org_id": "demo-org",
        "asset_id": "PUMP-101",
        "kind": "anomaly",
        "severity": "high",
        "summary": f"Event {event_id}",
        "details": {"source": "edge"},
        "lineage": {"channel": "kafka"},
    }


def test_edge_buffer_replays_events_in_fifo_order(tmp_path):
    buffer = EdgeEventBuffer(str(tmp_path / "edge.sqlite3"), max_events=10)
    buffer.buffer_event(_event("EV-1"), error="pg offline")
    buffer.buffer_event(_event("EV-2"), error="pg offline")

    replayed = []

    def store(_conn, evt):
        replayed.append(evt["event_id"])

    outcome = buffer.replay(object(), store, batch_size=10)

    assert outcome == {"replayed": 2, "remaining": 0, "error": None}
    assert replayed == ["EV-1", "EV-2"]
    snapshot = buffer.snapshot()
    assert snapshot["connectivity_status"] == "online"
    assert snapshot["buffered_event_count"] == 0
    assert snapshot["last_successful_central_write_at"]


def test_edge_buffer_preserves_failed_replay_for_retry(tmp_path):
    buffer = EdgeEventBuffer(str(tmp_path / "edge.sqlite3"), max_events=10)
    buffer.buffer_event(_event("EV-1"), error="pg offline")
    buffer.buffer_event(_event("EV-2"), error="pg offline")

    replayed = []

    def store(_conn, evt):
        replayed.append(evt["event_id"])
        if evt["event_id"] == "EV-1":
            raise RuntimeError("central write failed")

    outcome = buffer.replay(object(), store, batch_size=10)

    assert outcome["replayed"] == 0
    assert outcome["remaining"] == 2
    assert outcome["error"] == "central write failed"
    assert replayed == ["EV-1"]
    snapshot = buffer.snapshot()
    assert snapshot["connectivity_status"] == "degraded"
    assert snapshot["buffered_event_count"] == 2
    assert snapshot["last_error"] == "central write failed"