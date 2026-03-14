from maintenance_intelligence.genai.gateway import GenAIGateway

def test_parse_structured_fallback(monkeypatch):
    class FakeGW(GenAIGateway):
        def __init__(self): pass
    gw = FakeGW()
    # malformed text -> fallback
    obj = gw._parse_structured("nonsense")
    assert "hypothesis" in obj and isinstance(obj["confidence"], float)
