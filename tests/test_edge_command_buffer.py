from maintenance_intelligence.runner.edge_command_buffer import EdgeCommandBuffer


def test_edge_command_buffer_stores_single_active_command_per_proposal(tmp_path):
    queue = EdgeCommandBuffer(str(tmp_path / "edge-command.sqlite3"))

    first = queue.enqueue_command(
        "REC-1",
        {
            "proposal_id": "REC-1",
            "recommendation_id": "REC-1",
            "recommendation": {"id": "REC-1", "asset_id": "PUMP-101"},
        },
        error="cmms offline",
    )
    second = queue.enqueue_command(
        "REC-1",
        {
            "proposal_id": "REC-1",
            "recommendation_id": "REC-1",
            "recommendation": {"id": "REC-1", "asset_id": "PUMP-101", "title": "Retry"},
        },
        error="cmms still offline",
    )

    assert first["queue_id"] == second["queue_id"]
    assert queue.snapshot()["queued_command_count"] == 1
    assert queue.snapshot()["total_queued_commands"] == 1
    stored = queue.get_queued_command("REC-1")
    assert stored["proposal_id"] == "REC-1"
    assert stored["payload"]["recommendation"]["title"] == "Retry"
    assert stored["last_error"] == "cmms still offline"


def test_edge_command_buffer_tracks_replay_lifecycle(tmp_path):
    queue = EdgeCommandBuffer(str(tmp_path / "edge-command.sqlite3"))
    queue.enqueue_command(
        "REC-1",
        {
            "proposal_id": "REC-1",
            "recommendation_id": "REC-1",
            "recommendation": {"id": "REC-1", "asset_id": "PUMP-101"},
        },
        error="cmms offline",
    )

    queue.mark_replay_attempt_started()
    queue.record_replay_failure("REC-1", "still offline")
    failed = queue.get_queued_command("REC-1")
    assert failed["replay_attempts"] == 1
    assert failed["last_error"] == "still offline"

    queue.record_replay_success("REC-1")
    snapshot = queue.snapshot()
    assert snapshot["queued_command_count"] == 0
    assert snapshot["total_queued_commands"] == 1
    assert snapshot["total_replayed_commands"] == 1
    assert snapshot["total_replay_failures"] == 1
    assert snapshot["last_replay_attempt_at"]
    assert snapshot["last_successful_replay_at"]