from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services import rca_agent as rca_mod


class FakeMessage:
    def __init__(self, value):
        self.value = value


class FakeConsumer:
    def __init__(self, events):
        self._events = [FakeMessage(event) for event in events]
        self.closed = False

    def __iter__(self):
        return iter(self._events)

    def close(self):
        self.closed = True


class FakeProducer:
    def __init__(self):
        self.sent = []
        self.flushed = False
        self.closed = False

    def send(self, topic, payload):
        self.sent.append((topic, payload))

    def flush(self):
        self.flushed = True

    def close(self, timeout=10):
        self.closed = True


def test_rca_agent_loop_processes_event_end_to_end(monkeypatch, tmp_path):
    fake_event = {
        "org_id": "ORG-1",
        "asset_id": "PUMP-101",
        "kind": "alarm",
        "event_id": "EVT-1",
        "summary": "pump vibration high",
        "details": {"temperature": 88},
    }
    fake_consumer = FakeConsumer([fake_event])
    fake_producer = FakeProducer()
    written = {}
    gateway_calls = {}
    persisted = {"parts": []}

    class FakeGateway:
        def __init__(self, api_key, model, timeout_s):
            gateway_calls["init"] = {
                "api_key": api_key,
                "model": model,
                "timeout_s": timeout_s,
            }

        def call_rca(self, event, context):
            gateway_calls["event"] = event
            gateway_calls["context"] = context
            return {
                "text": "structured ok",
                "model_version": "gpt-4.1",
                "tokens": 42,
                "latency_ms": 12,
                "structured": {
                    "title": "Seal wear on pump",
                    "hypothesis": ["Bearing wear", "Unbalance"],
                    "evidence_ids": ["DOC-1", "SIG-1"],
                    "immediate_actions": ["Check bearing temp"],
                    "pm_suggestions": ["Increase lube cycle"],
                    "repair_plan": {
                        "parts_list": [
                            {"part_no": "BRG-9", "description": "Bearing kit", "qty": 1, "lead_time_days": 2}
                        ],
                        "tools_required": ["Dial indicator"],
                        "procedure_steps": [],
                        "estimated_duration_hrs": 1.5,
                        "safety_requirements": ["LOTO"],
                        "permit_type": "standard",
                        "spare_parts_cost_estimate": 250.0,
                    },
                    "confidence": 0.82,
                },
            }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(rca_mod.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(rca_mod, "create_kafka_consumer", lambda *_args, **_kwargs: fake_consumer)
    monkeypatch.setattr(rca_mod, "create_kafka_producer", lambda *_args, **_kwargs: fake_producer)
    monkeypatch.setattr(rca_mod, "GenAIGateway", FakeGateway)
    monkeypatch.setattr(
        rca_mod,
        "get_event_context",
        lambda evt, settings, fleet_wide=None: {
            "last_wo_titles": ["Prior seal replacement"],
            "doc_chunks": [{"chunk_id": "DOC-1", "asset_id": "PUMP-101", "source_scope": "local", "source": "manual.pdf"}],
            "recent_signals": [{"signal_id": "SIG-1"}],
            "context_scope": "local+fleet",
            "fleet_context_summary": {
                "external_ref_count": 1,
                "referenced_asset_ids": ["PUMP-202"],
                "referenced_sources": ["incident.md"],
                "current_asset_id": "PUMP-101",
            },
        },
    )
    monkeypatch.setattr(
        rca_mod,
        "write_run_summary",
        lambda dir_path, run_id, payload: written.setdefault("summary", payload) or str(tmp_path / "summary.json"),
    )
    monkeypatch.setattr(
        rca_mod,
        "create_repair_plan",
        lambda dsn, **kwargs: persisted.setdefault("plan", {"plan_id": "RP-123", **kwargs}),
    )
    monkeypatch.setattr(
        rca_mod,
        "add_part_to_plan",
        lambda dsn, plan_id, **kwargs: persisted["parts"].append({"plan_id": plan_id, **kwargs}) or {"part_id": "PART-123", "plan_id": plan_id, **kwargs},
    )

    rca_mod.rca_agent(kafka_bootstrap="kafka:9092")

    assert gateway_calls["init"]["api_key"] == "test-key"
    assert gateway_calls["event"]["event_id"] == "EVT-1"
    assert gateway_calls["context"]["doc_chunks"][0]["chunk_id"] == "DOC-1"

    assert len(fake_producer.sent) == 1
    topic, payload = fake_producer.sent[0]
    assert topic == "canonical.recommendation.created"
    assert payload["recommendation"]["asset_id"] == "PUMP-101"
    assert payload["recommendation"]["title"] == "Seal wear on pump"
    assert payload["recommendation"]["model"]["version"] == "gpt-4.1"
    assert payload["recommendation"]["evidence"] == ["EVT-1", "DOC-1", "SIG-1"]
    assert payload["recommendation"]["repair_plan"]["plan_id"] == "RP-123"

    assert written["summary"]["event_id"] == "EVT-1"
    assert written["summary"]["structured"]["pm_suggestions"] == ["Increase lube cycle"]
    assert written["summary"]["repair_plan_id"] == "RP-123"
    assert written["summary"]["context_meta"]["asset_id"] == "PUMP-101"
    assert written["summary"]["context_meta"]["org_id"] == "ORG-1"
    assert written["summary"]["context_meta"]["doc_chunk_ids"] == ["DOC-1"]
    assert written["summary"]["context_meta"]["signal_ids"] == ["SIG-1"]
    assert written["summary"]["context_scope"] == "local+fleet"
    assert written["summary"]["fleet_context_summary"]["external_ref_count"] == 1
    assert written["summary"]["context_items"]["doc_chunks"][0]["source_scope"] == "local"
    assert persisted["plan"]["recommendation_id"] == payload["recommendation"]["id"]
    assert persisted["plan"]["asset_id"] == "PUMP-101"
    assert persisted["parts"][0]["plan_id"] == "RP-123"
    assert persisted["parts"][0]["name"] == "BRG-9"
    assert persisted["parts"][0]["metadata"] == {"part_no": "BRG-9", "lead_time_days": 2}

    assert fake_producer.flushed is True
    assert fake_consumer.closed is True
    assert fake_producer.closed is True


def test_process_event_logs_and_continues_when_repair_plan_persistence_fails(monkeypatch, tmp_path):
    warnings = []
    written = {}
    sent = {}

    class FakeGateway:
        def call_rca(self, event, context):
            return {
                "text": "structured ok",
                "model_version": "gpt-4.1",
                "tokens": 42,
                "latency_ms": 12,
                "structured": {
                    "title": "Seal wear on pump",
                    "summary": "Bearing replacement required",
                    "hypothesis": ["Bearing wear"],
                    "evidence_ids": [],
                    "immediate_actions": [],
                    "pm_suggestions": [],
                    "repair_plan": {
                        "parts_list": [{"part_no": "BRG-9", "description": "Bearing kit", "qty": 1, "lead_time_days": 2}],
                        "tools_required": [],
                        "procedure_steps": [],
                        "estimated_duration_hrs": 1.5,
                        "safety_requirements": [],
                        "permit_type": "",
                        "spare_parts_cost_estimate": 250.0,
                    },
                    "confidence": 0.82,
                },
            }

    monkeypatch.setattr(rca_mod, "get_event_context", lambda evt, settings, fleet_wide=None: {"last_wo_titles": [], "doc_chunks": [], "recent_signals": [], "context_scope": "local", "fleet_context_summary": {"external_ref_count": 0, "referenced_asset_ids": [], "referenced_sources": [], "current_asset_id": "PUMP-101"}})
    monkeypatch.setattr(rca_mod, "send_recommendation", lambda producer, recommendation: sent.setdefault("event", recommendation))
    monkeypatch.setattr(rca_mod, "write_run_summary", lambda dir_path, run_id, payload: written.setdefault("payload", payload) or str(tmp_path / "summary.json"))
    monkeypatch.setattr(rca_mod, "create_repair_plan", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(rca_mod.logger, "warning", lambda payload: warnings.append(payload))

    result = rca_mod.process_event(
        {"org_id": "ORG-1", "asset_id": "PUMP-101", "kind": "alarm", "event_id": "EVT-1"},
        Settings(),
        producer=object(),
        gateway=FakeGateway(),
    )

    assert result is not None
    assert sent["event"]["recommendation"]["repair_plan"].get("plan_id") is None
    assert "repair_plan_id" not in written["payload"]
    assert warnings[0]["event"] == "rca.repair_plan.persistence_failed"