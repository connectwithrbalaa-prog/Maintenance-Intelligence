from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services import rca_agent as rca_mod


def test_process_event_uses_deterministic_local_fallback_when_edge_mode_has_no_gateway(monkeypatch, tmp_path):
    written = {}
    sent = {}

    monkeypatch.setattr(
        rca_mod,
        "get_event_context",
        lambda evt, settings: {
            "last_wo_titles": ["Inspect seal housing"],
            "doc_chunks": [{"chunk_id": "DOC-1"}],
            "recent_signals": [{"signal_id": "SIG-1"}],
            "context_scope": "local",
            "fleet_context_summary": {"external_ref_count": 0, "referenced_asset_ids": [], "referenced_sources": [], "current_asset_id": evt.get("asset_id")},
        },
    )
    monkeypatch.setattr(rca_mod, "send_recommendation", lambda producer, recommendation: sent.setdefault("event", recommendation))
    monkeypatch.setattr(rca_mod, "write_run_summary", lambda dir_path, run_id, payload: written.setdefault("payload", payload) or str(tmp_path / "summary.json"))
    monkeypatch.setattr(rca_mod, "create_repair_plan", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not persist empty repair plan")))

    result = rca_mod.process_event(
        {"org_id": "O1", "asset_id": "A1", "kind": "alarm", "event_id": "E1", "summary": "High vibration"},
        Settings(edge_mode_enabled=True),
        producer=object(),
        gateway=None,
    )

    assert result is not None
    assert sent["event"]["lineage"]["source"] == "agent-rca-edge-local-fallback"
    assert sent["event"]["recommendation"]["model"]["name"] == "local-deterministic"
    assert sent["event"]["recommendation"]["model"]["version"] == "edge-fallback-v1"
    assert sent["event"]["recommendation"]["evidence"] == ["E1", "DOC-1", "SIG-1"]
    assert written["payload"]["structured"]["title"] == "Local fallback RCA for A1"
    assert "GenAI was unavailable" in written["payload"]["structured"]["summary"]
    assert written["payload"]["context_meta"]["inference_mode"] == "local-deterministic"
    assert written["payload"]["context_meta"]["degraded_inference"] is True
    assert "repair_plan_id" not in written["payload"]


def test_process_event_uses_deterministic_local_fallback_when_gateway_reports_genai_error(monkeypatch, tmp_path):
    written = {}
    sent = {}

    class FakeGateway:
        def call_rca(self, event, context):
            return {
                "text": "[GENAI_ERROR] upstream timeout",
                "model_version": "gpt-4.1",
                "tokens": None,
                "latency_ms": 55,
                "structured": {"title": "RCA Draft", "confidence": 0.5},
            }

    monkeypatch.setattr(
        rca_mod,
        "get_event_context",
        lambda evt, settings, fleet_wide=None: {
            "last_wo_titles": [],
            "doc_chunks": [{"chunk_id": "DOC-2"}],
            "recent_signals": [{"signal_id": "SIG-9"}],
            "context_scope": "local+fleet",
            "fleet_context_summary": {"external_ref_count": 1, "referenced_asset_ids": ["PUMP-9"], "referenced_sources": ["incident.md"], "current_asset_id": evt.get("asset_id")},
        },
    )
    monkeypatch.setattr(rca_mod, "send_recommendation", lambda producer, recommendation: sent.setdefault("event", recommendation))
    monkeypatch.setattr(rca_mod, "write_run_summary", lambda dir_path, run_id, payload: written.setdefault("payload", payload) or str(tmp_path / "summary.json"))
    monkeypatch.setattr(rca_mod, "create_repair_plan", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not persist empty repair plan")))

    result = rca_mod.process_event(
        {"org_id": "ORG-1", "asset_id": "PUMP-101", "kind": "anomaly", "event_id": "EVT-1", "summary": "pump vibration high"},
        Settings(edge_mode_enabled=True),
        producer=object(),
        gateway=FakeGateway(),
    )

    assert result is not None
    assert sent["event"]["recommendation"]["model"]["name"] == "local-deterministic"
    assert sent["event"]["recommendation"]["title"] == "Local fallback RCA for PUMP-101"
    assert written["payload"]["context_scope"] == "local+fleet"
    assert written["payload"]["context_meta"]["inference_mode"] == "local-deterministic"
    assert written["payload"]["structured"]["evidence_ids"] == ["EVT-1", "DOC-2", "SIG-9"]