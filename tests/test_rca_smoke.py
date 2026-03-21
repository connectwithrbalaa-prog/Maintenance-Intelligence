from maintenance_intelligence.services import rca_agent as rca_mod
from maintenance_intelligence.runner.config import Settings


def test_process_event_ignores_non_alarm_events(monkeypatch):
    monkeypatch.setattr(
        rca_mod,
        "get_event_context",
        lambda evt, settings: (_ for _ in ()).throw(AssertionError("should not assemble context")),
    )

    result = rca_mod.process_event(
        {"org_id": "O1", "asset_id": "A1", "kind": "info", "event_id": "E1"},
        Settings(),
        producer=object(),
        gateway=None,
    )

    assert result is None
