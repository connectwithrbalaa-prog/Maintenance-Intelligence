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
        lambda evt, settings: {
            "last_wo_titles": ["Prior seal replacement"],
            "doc_chunks": [{"chunk_id": "DOC-1"}],
            "recent_signals": [{"signal_id": "SIG-1"}],
        },
    )
    monkeypatch.setattr(
        rca_mod,
        "write_run_summary",
        lambda dir_path, run_id, payload: written.setdefault("summary", payload)
        or str(tmp_path / "summary.json"),
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

    assert written["summary"]["event_id"] == "EVT-1"
    assert written["summary"]["structured"]["pm_suggestions"] == ["Increase lube cycle"]
    assert written["summary"]["context_meta"]["doc_chunk_ids"] == ["DOC-1"]

    assert fake_producer.flushed is True
    assert fake_consumer.closed is True
    assert fake_producer.closed is True
