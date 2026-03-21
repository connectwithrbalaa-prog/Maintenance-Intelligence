from maintenance_intelligence.services import rca_agent as rca_mod
from maintenance_intelligence.runner.config import Settings


def test_agent_structured_mock(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")

    class FakeGW:
        def call_rca(self, event, context):
            return {
                "text": "ok",
                "model_version": "gpt-4.1",
                "tokens": 42,
                "latency_ms": 12,
                "structured": {
                    "title": "Seal wear on pump",
                    "hypothesis": ["Bearing wear", "Unbalance"],
                    "evidence_ids": ["DOC-1", "SIG-1"],
                    "immediate_actions": ["Check bearing temp"],
                    "pm_suggestions": ["Increase lube cycle"],
                    "confidence": 0.82,
                },
            }

    written = {}
    sent = {}

    monkeypatch.setattr(
        rca_mod,
        "get_event_context",
        lambda evt, settings, **kwargs: {
            "last_wo_titles": [],
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

    result = rca_mod.process_event(
        {"org_id": "O1", "asset_id": "A1", "kind": "alarm", "event_id": "E1"},
        Settings(),
        producer=object(),
        gateway=FakeGW(),
    )

    assert result is not None
    assert written["payload"]["structured"]["confidence"] == 0.82
    assert written["payload"]["structured"]["title"] == "Seal wear on pump"
    assert written["payload"]["model"]["version"] == "gpt-4.1"
    assert sent["event"]["recommendation"]["title"] == "Seal wear on pump"
    assert sent["event"]["recommendation"]["evidence"] == ["E1", "DOC-1", "SIG-1"]
