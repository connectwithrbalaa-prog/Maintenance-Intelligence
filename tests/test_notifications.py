import json

from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services import notifications as notifications_mod


def test_emit_notification_matches_most_specific_routes_and_supports_fanout(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            [
                {"route_id": "default", "webhook_url": "https://hooks.example.test/default", "minimum_severity": "warning"},
                {
                    "route_id": "org-failure-a",
                    "webhook_url": "https://hooks.example.test/ops-a",
                    "org_ids": ["demo-org"],
                    "event_types": ["cmms.terminal_failure"],
                    "minimum_severity": "warning",
                },
                {
                    "route_id": "org-failure-b",
                    "webhook_url": "https://hooks.example.test/ops-b",
                    "org_ids": ["demo-org"],
                    "event_types": ["cmms.terminal_failure"],
                    "minimum_severity": "warning",
                },
                {
                    "route_id": "site-critical",
                    "webhook_url": "https://hooks.example.test/site-a",
                    "org_ids": ["demo-org"],
                    "site_ids": ["site-a"],
                    "event_types": ["cmms.terminal_failure"],
                    "severities": ["critical"],
                },
            ]
        ),
    )
    deliveries = []

    def fake_send(url, payload, timeout_s):
        deliveries.append({"url": url, "payload": payload, "timeout_s": timeout_s})
        return True, 202, ""

    monkeypatch.setattr(notifications_mod, "_send_webhook", fake_send)

    first = notifications_mod.emit_notification(
        event_type="cmms.terminal_failure",
        severity="warning",
        summary="Terminal CMMS failure for demo-org",
        org_id="demo-org",
        site_id="site-b",
        dedupe_key="fanout-warning",
        payload={"proposal_id": "REC-101"},
        settings=Settings(),
    )

    assert first["status"] == "sent"
    assert first["delivery_count"] == 2
    assert [item["route_id"] for item in first["deliveries"]] == ["org-failure-a", "org-failure-b"]
    assert [item["url"] for item in deliveries] == [
        "https://hooks.example.test/ops-a",
        "https://hooks.example.test/ops-b",
    ]

    second = notifications_mod.emit_notification(
        event_type="cmms.terminal_failure",
        severity="critical",
        summary="Critical CMMS failure for site-a",
        org_id="demo-org",
        site_id="site-a",
        dedupe_key="site-critical",
        payload={"proposal_id": "REC-202"},
        settings=Settings(),
    )

    assert second["status"] == "sent"
    assert second["delivery_count"] == 1
    assert second["deliveries"][0]["route_id"] == "site-critical"
    assert deliveries[-1]["url"] == "https://hooks.example.test/site-a"

    records = notifications_mod.recent_notification_deliveries(limit=10, settings=Settings())
    assert [record["route_id"] for record in records[:3]] == ["site-critical", "org-failure-a", "org-failure-b"]


def test_emit_notification_falls_back_to_default_route_when_no_specific_rule_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            {
                "default": {"webhook_url": "https://hooks.example.test/default", "minimum_severity": "warning"},
                "demo-org": {"webhook_url": "https://hooks.example.test/demo-org", "minimum_severity": "warning"},
            }
        ),
    )
    deliveries = []

    def fake_send(url, payload, timeout_s):
        deliveries.append(url)
        return True, 204, ""

    monkeypatch.setattr(notifications_mod, "_send_webhook", fake_send)

    result = notifications_mod.emit_notification(
        event_type="edge.degraded",
        severity="critical",
        summary="Unknown org edge degradation",
        org_id="other-org",
        dedupe_key="fallback-default",
        payload={"connectivity_status": "offline"},
        settings=Settings(),
    )

    assert result["status"] == "sent"
    assert result["delivery_count"] == 1
    assert result["deliveries"][0]["route_id"] == "default"
    assert deliveries == ["https://hooks.example.test/default"]