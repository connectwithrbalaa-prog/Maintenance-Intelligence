import os, json
from maintenance_intelligence.services import rca_agent as rca_mod
from maintenance_intelligence.runner.config import Settings

def test_agent_structured_mock(monkeypatch, tmp_path):
    # Force gateway path but with mocked call
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    class FakeGW:
        def call_rca(self, event, context):
            return {"text":"ok", "model_version":"gpt-4.1", "tokens":42, "latency_ms":12,
                    "structured":{
                        "title":"Seal wear on pump",
                        "hypothesis":["Bearing wear", "Unbalance"],
                        "evidence_ids":["DOC-1","SIG-1"],
                        "immediate_actions":["Check bearing temp"],
                        "pm_suggestions":["Increase lube cycle"],
                        "confidence":0.82}}
    monkeypatch.setattr(rca_mod, "GenAIGateway", lambda **k: FakeGW())

    class FakeCons:
        def __iter__(self): return iter([type("M", (), {"value": {"org_id":"O1","asset_id":"A1","kind":"alarm","event_id":"E1"}})()])
    class FakeProd:
        def send(self, *_a, **_k): pass
        def flush(self): pass

    monkeypatch.setattr(rca_mod, "KafkaConsumer", lambda *a, **k: FakeCons())
    monkeypatch.setattr(rca_mod, "KafkaProducer", lambda *a, **k: FakeProd())

    from maintenance_intelligence.runner import summaries as S
    written = {}
    def fake_write(dir_path, run_id, payload):
        written["p"] = payload
        return str(tmp_path / "summary.json")
    monkeypatch.setattr(S, "write_run_summary", fake_write)

    # Run single-iteration inline
    settings = Settings()
    cons = FakeCons(); prod = FakeProd()
    for msg in cons:
        evt = msg.value
        if evt.get("kind") not in ("alarm","anomaly"): continue
        # mimic logic enough to generate payload
        # validate structured shape via summary writer
        break
    assert "p" in written
    assert "structured" in written["p"]["model"] or "structured" in written["p"]
