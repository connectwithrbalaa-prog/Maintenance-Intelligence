from maintenance_intelligence.context.assembler import get_event_context
def test_context_smoke():
    evt = {"asset_id":"TEST-ASSET","kind":"alarm"}
    ctx = get_event_context(evt)
    assert "asset_id" in ctx
