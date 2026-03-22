from types import SimpleNamespace

import maintenance_intelligence.genai.gateway as gateway_mod
from maintenance_intelligence.genai.gateway import GenAIGateway


def test_build_prompt_includes_structured_repair_plan_schema():
    class FakeGW(GenAIGateway):
        def __init__(self):
            pass

    gw = FakeGW()
    prompt = gw._build_prompt({"event_id": "EVT-1"}, {"asset_id": "PUMP-101"})

    assert "Respond with STRICT JSON only" in prompt
    assert '"repair_plan"' in prompt
    assert '"parts_list"' in prompt
    assert "Event:" in prompt
    assert "Asset:" in prompt


def test_parse_structured_fallback(monkeypatch):
    class FakeGW(GenAIGateway):
        def __init__(self):
            pass

    gw = FakeGW()
    # malformed text -> fallback
    obj = gw._parse_structured("nonsense")
    assert "hypothesis" in obj and isinstance(obj["confidence"], float)
    assert "repair_plan" in obj and isinstance(obj["repair_plan"], dict)
    assert obj["repair_plan"]["parts_list"] == []


def test_parse_structured_adds_defaults_and_clamps_confidence():
    class FakeGW(GenAIGateway):
        def __init__(self):
            pass

    gw = FakeGW()
    obj = gw._parse_structured('{"title":"Draft","confidence": 7, "repair_plan": []}')

    assert obj["title"] == "Draft"
    assert obj["summary"] == ""
    assert obj["confidence"] == 1.0
    assert obj["repair_plan"]["tools_required"] == []
    assert obj["repair_plan"]["permit_type"] == ""


def test_call_rca_returns_tokens_and_parsed_structure(monkeypatch):
    class FakeResponse:
        def __init__(self):
            self.choices = [
                SimpleNamespace(
                    message=SimpleNamespace(content='{"title":"Bearing issue","confidence":0.9}')
                )
            ]
            self.usage = SimpleNamespace(total_tokens=321)

    calls = []

    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: calls.append(kwargs) or FakeResponse()
                )
            )

    monkeypatch.setattr(gateway_mod, "OpenAI", FakeClient)

    gw = GenAIGateway(api_key="secret", model="gpt-4.1-mini", timeout_s=13)
    result = gw.call_rca({"event_id": "EVT-1"}, {"asset_id": "PUMP-101"})

    assert calls[0]["model"] == "gpt-4.1-mini"
    assert calls[0]["temperature"] == 0.2
    assert calls[0]["timeout"] == 13
    assert result["tokens"] == 321
    assert result["model_version"] == "gpt-4.1-mini"
    assert result["structured"]["title"] == "Bearing issue"
    assert result["structured"]["confidence"] == 0.9


def test_call_rca_returns_error_text_and_fallback_structure_on_client_failure(monkeypatch):
    error_events = []

    class FakeClient:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: (_ for _ in ()).throw(
                        RuntimeError("timeout talking to model")
                    )
                )
            )

    monkeypatch.setattr(gateway_mod, "OpenAI", FakeClient)
    monkeypatch.setattr(gateway_mod.logger, "error", lambda payload: error_events.append(payload))

    gw = GenAIGateway(api_key="secret", model="gpt-4.1-mini")
    result = gw.call_rca({"event_id": "EVT-1"}, {"asset_id": "PUMP-101"})

    assert result["tokens"] is None
    assert result["text"].startswith("[GENAI_ERROR] timeout talking to model")
    assert result["structured"]["title"] == "RCA Draft"
    assert result["structured"]["repair_plan"]["parts_list"] == []
    assert error_events == [{"event": "genai.error", "err": "timeout talking to model"}]
