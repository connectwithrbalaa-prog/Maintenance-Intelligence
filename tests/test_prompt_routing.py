
from maintenance_intelligence.api.metrics import (
    rca_cost_usd_total,
    rca_latency_seconds,
    rca_runs_by_prompt_total,
)
from maintenance_intelligence.services import rca_agent as rca_mod


def test_rca_agent_records_prompt_metadata_and_metric(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("MI_RCA_MODEL_RATES", '{"gpt-4.1": 1.0}')

    class FakeCons:
        def __iter__(self):
            return iter([type("M", (), {"value": {"org_id": "ORG-1", "asset_id": "A1", "kind": "alarm", "event_id": "E1"}})()])

        def close(self):
            return None

    class FakeProd:
        def close(self, timeout=10):
            return None

    class FakeGW:
        def __init__(self, **kwargs):
            pass

        def call_rca(self, event, context, prompt_selection=None):
            return {
                "text": "ok",
                "model_version": "gpt-4.1",
                "tokens": 42,
                "latency_ms": 12,
                "structured": {
                    "title": "Seal wear on pump",
                    "hypothesis": ["Bearing wear"],
                    "evidence_ids": ["DOC-1"],
                    "immediate_actions": ["Check bearing temp"],
                    "pm_suggestions": ["Increase lube cycle"],
                    "confidence": 0.82,
                },
            }

    written = {}

    monkeypatch.setattr(rca_mod, "create_kafka_consumer", lambda *_a, **_k: FakeCons())
    monkeypatch.setattr(rca_mod, "create_kafka_producer", lambda *_a, **_k: FakeProd())
    monkeypatch.setattr(rca_mod, "GenAIGateway", FakeGW)
    monkeypatch.setattr(rca_mod, "get_event_context", lambda evt, settings, org_id=None: {"doc_chunks": [{"chunk_id": "DOC-1"}], "recent_signals": []})
    monkeypatch.setattr(
        rca_mod,
        "resolve_prompt_for_route",
        lambda route_name, org_id, subject_key, settings=None: {
            "prompt": {"prompt_id": "rca-canary-v1", "system_prompt": "sys", "user_prompt_template": "Event {event_json}"},
            "prompt_id": "rca-canary-v1",
            "variant": "canary",
            "route_name": "rca",
            "auto_rollback_triggered": False,
        },
    )
    monkeypatch.setattr(rca_mod, "send_recommendation", lambda *args, **kwargs: None)

    def fake_write(dir_path, run_id, payload):
        written["payload"] = payload
        return str(tmp_path / "summary.json")

    monkeypatch.setattr(rca_mod, "write_run_summary", fake_write)

    before = rca_runs_by_prompt_total.labels(service="rca_agent", route="rca", prompt_id="rca-canary-v1", variant="canary")._value.get()
    before_cost = rca_cost_usd_total.labels(model="gpt-4.1", prompt_id="rca-canary-v1")._value.get()
    before_latency = rca_latency_seconds.labels(service="rca_agent", model="gpt-4.1", prompt_id="rca-canary-v1")._sum.get()
    rca_mod.rca_agent("kafka:9092")
    after = rca_runs_by_prompt_total.labels(service="rca_agent", route="rca", prompt_id="rca-canary-v1", variant="canary")._value.get()
    after_cost = rca_cost_usd_total.labels(model="gpt-4.1", prompt_id="rca-canary-v1")._value.get()
    after_latency = rca_latency_seconds.labels(service="rca_agent", model="gpt-4.1", prompt_id="rca-canary-v1")._sum.get()

    assert after == before + 1
    assert round(after_cost - before_cost, 6) == 0.042
    assert round(after_latency - before_latency, 6) == 0.012
    assert written["payload"]["prompt"]["prompt_id"] == "rca-canary-v1"
    assert written["payload"]["metrics"]["estimated_cost_usd"] == 0.042
    assert written["payload"]["model"]["estimated_cost_usd"] == 0.042
    assert written["payload"]["model"]["prompt_variant"] == "canary"