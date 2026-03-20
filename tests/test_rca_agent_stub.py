from maintenance_intelligence.services import rca_agent as rca_mod
from maintenance_intelligence.runner.config import Settings


def test_rca_agent_stub_path(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    written = {}
    sent = {}
    notifications = []

    monkeypatch.setattr(
        rca_mod,
        "get_event_context",
        lambda evt, settings: {
            "last_wo_titles": ["Inspect seal housing"],
            "doc_chunks": [{"chunk_id": "DOC-1"}],
            "recent_signals": [{"signal_id": "SIG-1"}],
        },
    )
    monkeypatch.setattr(
        rca_mod,
        "send_recommendation",
        lambda producer, recommendation: sent.setdefault("event", recommendation),
    )
    monkeypatch.setattr(
        rca_mod,
        "write_run_summary",
        lambda dir_path, run_id, payload: written.setdefault("payload", payload)
        or str(tmp_path / "summary.json"),
    )
    monkeypatch.setattr(
        rca_mod,
        "create_repair_plan",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("should not persist empty repair plan")
        ),
    )
    monkeypatch.setattr(
        rca_mod,
        "emit_notification",
        lambda **kwargs: notifications.append(kwargs) or {"status": "sent"},
    )

    result = rca_mod.process_event(
        {"org_id": "O1", "asset_id": "A1", "kind": "alarm", "event_id": "E1"},
        Settings(),
        producer=object(),
        gateway=None,
    )

    assert result is not None
    assert sent["event"]["recommendation"]["asset_id"] == "A1"
    assert sent["event"]["recommendation"]["model"]["version"] == "unset"
    assert sent["event"]["recommendation"]["evidence"] == ["E1", "DOC-1", "SIG-1"]
    assert written["payload"]["structured"]["title"] == "RCA Draft"
    assert written["payload"]["context_meta"]["asset_id"] == "A1"
    assert written["payload"]["context_meta"]["org_id"] == "O1"
    assert written["payload"]["context_meta"]["doc_chunk_ids"] == ["DOC-1"]
    assert written["payload"]["context_meta"]["signal_ids"] == ["SIG-1"]
    assert "repair_plan_id" not in written["payload"]
    assert len(notifications) == 1
    assert notifications[0]["event_type"] == "rca.completed"
    assert notifications[0]["org_id"] == "O1"
