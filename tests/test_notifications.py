import json

from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services import notifications as notifications_mod


def test_emit_notification_matches_most_specific_routes_and_supports_fanout(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            [
                {
                    "route_id": "default",
                    "webhook_url": "https://hooks.example.test/default",
                    "minimum_severity": "warning",
                },
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
    assert records[0]["route_id"] == "site-critical"
    assert {record["route_id"] for record in records[1:3]} == {
        "org-failure-a",
        "org-failure-b",
    }


def test_emit_notification_falls_back_to_default_route_when_no_specific_rule_matches(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            {
                "default": {
                    "webhook_url": "https://hooks.example.test/default",
                    "minimum_severity": "warning",
                },
                "demo-org": {
                    "webhook_url": "https://hooks.example.test/demo-org",
                    "minimum_severity": "warning",
                },
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


def test_list_notification_routes_and_preview_match_explanations(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            [
                {
                    "route_id": "default",
                    "webhook_url": "https://hooks.example.test/default",
                    "minimum_severity": "warning",
                },
                {
                    "route_id": "org-terminal",
                    "webhook_url": "https://hooks.example.test/org-terminal",
                    "org_ids": ["demo-org"],
                    "event_types": ["cmms.terminal_failure"],
                    "minimum_severity": "warning",
                    "priority": 1,
                },
                {
                    "route_id": "site-critical",
                    "webhook_url": "https://hooks.example.test/site-critical",
                    "org_ids": ["demo-org"],
                    "site_ids": ["site-a"],
                    "event_types": ["cmms.terminal_failure"],
                    "severities": ["critical"],
                    "priority": 2,
                },
            ]
        ),
    )

    routes = notifications_mod.list_notification_routes(settings=Settings())
    assert [route["route_id"] for route in routes] == ["site-critical", "org-terminal", "default"]
    assert routes[0]["destination"] == "hooks.example.test"
    assert routes[0]["specificity"] == 4

    preview = notifications_mod.preview_notification_routes(
        org_id="demo-org",
        site_id="site-a",
        event_type="cmms.terminal_failure",
        severity="critical",
        settings=Settings(),
    )

    assert preview["selected_routes"][0]["route_id"] == "site-critical"
    evaluations = {item["route_id"]: item for item in preview["evaluated_routes"]}
    assert evaluations["site-critical"]["selected"] is True
    assert "lower_specificity_than_selected" in evaluations["org-terminal"]["reasons"]
    assert "lower_specificity_than_selected" in evaluations["default"]["reasons"]


def test_recent_notification_deliveries_supports_route_edge_and_sort_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            [
                {
                    "route_id": "default",
                    "webhook_url": "https://hooks.example.test/default",
                    "minimum_severity": "warning",
                },
                {
                    "route_id": "edge-route",
                    "webhook_url": "https://hooks.example.test/edge",
                    "event_types": ["edge.degraded"],
                    "minimum_severity": "warning",
                },
            ]
        ),
    )

    def fake_send(url, payload, timeout_s):
        if payload["event_type"] == "edge.degraded":
            return False, 503, "edge route unavailable"
        return True, 202, ""

    monkeypatch.setattr(notifications_mod, "_send_webhook", fake_send)

    notifications_mod.emit_notification(
        event_type="cmms.terminal_failure",
        severity="critical",
        summary="Terminal failure",
        org_id="demo-org",
        site_id="site-a",
        dedupe_key="service-sort-1",
        payload={"proposal_id": "REC-1"},
        settings=Settings(),
    )
    notifications_mod.emit_notification(
        event_type="edge.degraded",
        severity="warning",
        summary="Edge offline",
        org_id="demo-org",
        site_id="site-a",
        dedupe_key="service-sort-2",
        payload={
            "connectivity_status": "offline",
            "buffered_event_count": 3,
            "queued_command_count": 2,
            "transition_count": 5,
        },
        settings=Settings(),
    )

    failures_first = notifications_mod.recent_notification_deliveries(
        limit=10,
        sort="failures_first",
        settings=Settings(),
    )
    assert failures_first[0]["status"] == "failed"
    assert failures_first[0]["edge_connectivity_status"] == "offline"
    assert failures_first[0]["edge_buffered_event_count"] == 3
    assert failures_first[0]["edge_queued_command_count"] == 2
    assert failures_first[0]["edge_transition_count"] == 5

    edge_only = notifications_mod.recent_notification_deliveries(
        limit=10,
        event_type="edge.degraded",
        edge_state="offline",
        route_id="edge-route",
        sort="recent",
        settings=Settings(),
    )
    assert len(edge_only) == 1
    assert edge_only[0]["route_id"] == "edge-route"
    assert edge_only[0]["status"] == "failed"

    oldest = notifications_mod.recent_notification_deliveries(
        limit=10,
        sort="oldest",
        settings=Settings(),
    )
    assert oldest[-1]["event_type"] == "edge.degraded"


def test_recent_notification_deliveries_unknown_status_falls_back_to_all(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            {
                "default": {
                    "webhook_url": "https://hooks.example.test/default",
                    "minimum_severity": "warning",
                }
            }
        ),
    )

    def fake_send(url, payload, timeout_s):
        if payload["event_type"] == "edge.degraded":
            return False, 503, "edge route unavailable"
        return True, 202, ""

    monkeypatch.setattr(notifications_mod, "_send_webhook", fake_send)

    notifications_mod.emit_notification(
        event_type="cmms.terminal_failure",
        severity="critical",
        summary="Terminal failure",
        org_id="demo-org",
        dedupe_key="service-status-fallback-1",
        payload={"proposal_id": "REC-1"},
        settings=Settings(),
    )
    notifications_mod.emit_notification(
        event_type="edge.degraded",
        severity="warning",
        summary="Edge offline",
        org_id="demo-org",
        dedupe_key="service-status-fallback-2",
        payload={"connectivity_status": "offline"},
        settings=Settings(),
    )

    records = notifications_mod.recent_notification_deliveries(
        limit=10,
        status="not-a-status",
        settings=Settings(),
    )

    assert len(records) == 2
    assert {record["event_type"] for record in records} == {
        "cmms.terminal_failure",
        "edge.degraded",
    }


def test_recent_notification_deliveries_unknown_severity_falls_back_to_all(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            {
                "default": {
                    "webhook_url": "https://hooks.example.test/default",
                    "minimum_severity": "warning",
                }
            }
        ),
    )

    def fake_send(url, payload, timeout_s):
        if payload["event_type"] == "edge.degraded":
            return False, 503, "edge route unavailable"
        return True, 202, ""

    monkeypatch.setattr(notifications_mod, "_send_webhook", fake_send)

    notifications_mod.emit_notification(
        event_type="cmms.terminal_failure",
        severity="critical",
        summary="Terminal failure",
        org_id="demo-org",
        dedupe_key="service-severity-fallback-1",
        payload={"proposal_id": "REC-1"},
        settings=Settings(),
    )
    notifications_mod.emit_notification(
        event_type="edge.degraded",
        severity="warning",
        summary="Edge offline",
        org_id="demo-org",
        dedupe_key="service-severity-fallback-2",
        payload={"connectivity_status": "offline"},
        settings=Settings(),
    )

    records = notifications_mod.recent_notification_deliveries(
        limit=10,
        severity="not-a-severity",
        settings=Settings(),
    )

    assert len(records) == 2
    assert {record["event_type"] for record in records} == {
        "cmms.terminal_failure",
        "edge.degraded",
    }


def test_emit_notification_supports_email_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            [
                {
                    "route_id": "email-route",
                    "email_to": ["ops@example.test", "lead@example.test"],
                    "event_types": ["rca.completed"],
                    "minimum_severity": "info",
                }
            ]
        ),
    )
    monkeypatch.setenv("MI_NOTIFICATION_SMTP_HOST", "smtp.example.test")

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = host
            sent["port"] = port
            sent["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            return None

        def login(self, username, password):
            sent["login"] = username

        def send_message(self, message):
            sent["to"] = message["To"]
            sent["subject"] = message["Subject"]

    monkeypatch.setattr(notifications_mod.smtplib, "SMTP", FakeSMTP)

    result = notifications_mod.emit_notification(
        event_type="rca.completed",
        severity="info",
        summary="RCA completed",
        org_id="demo-org",
        site_id="site-a",
        dedupe_key="email-route-1",
        payload={"run_id": "RUN-1"},
        settings=Settings(),
    )

    assert result["status"] == "sent"
    assert result["delivery_count"] == 1
    assert result["deliveries"][0]["channel"] == "email"
    assert sent["host"] == "smtp.example.test"
    assert "ops@example.test" in sent["to"]
    records = notifications_mod.recent_notification_deliveries(limit=5, settings=Settings())
    assert records[0]["channel"] == "email"
    assert records[0]["event_type"] == "rca.completed"


def test_emit_notification_applies_policy_suppression_and_escalation(tmp_path, monkeypatch):
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            [
                {
                    "route_id": "default",
                    "webhook_url": "https://hooks.example.test/default",
                    "minimum_severity": "warning",
                }
            ]
        ),
    )
    monkeypatch.setenv(
        "MI_NOTIFICATION_POLICY_JSON",
        json.dumps(
            {
                "suppressions": [
                    {
                        "event_types": ["edge.degraded"],
                        "org_ids": ["org-1"],
                        "reason": "maintenance-window",
                    }
                ],
                "escalation": {
                    "event_types": ["cmms.exception"],
                    "org_ids": ["org-1"],
                    "failure_threshold": 2,
                    "window_s": 3600,
                },
            }
        ),
    )

    sent = []

    def fake_send(url, payload, timeout_s):
        sent.append(payload)
        return False, 503, "down"

    monkeypatch.setattr(notifications_mod, "_send_webhook", fake_send)

    suppressed = notifications_mod.emit_notification(
        event_type="edge.degraded",
        severity="warning",
        summary="Edge degraded",
        org_id="org-1",
        site_id="site-a",
        dedupe_key="policy-suppressed-1",
        payload={},
        settings=Settings(),
    )
    assert suppressed["status"] == "suppressed"
    assert suppressed["deliveries"][0]["delivery_error"] == "maintenance-window"

    first = notifications_mod.emit_notification(
        event_type="cmms.exception",
        severity="warning",
        summary="retryable failure",
        org_id="org-1",
        site_id="site-a",
        dedupe_key="policy-escalate-1",
        payload={"attempt": 1},
        settings=Settings(),
    )
    second = notifications_mod.emit_notification(
        event_type="cmms.exception",
        severity="warning",
        summary="retryable failure",
        org_id="org-1",
        site_id="site-a",
        dedupe_key="policy-escalate-2",
        payload={"attempt": 2},
        settings=Settings(),
    )
    third = notifications_mod.emit_notification(
        event_type="cmms.exception",
        severity="warning",
        summary="retryable failure",
        org_id="org-1",
        site_id="site-a",
        dedupe_key="policy-escalate-3",
        payload={"attempt": 3},
        settings=Settings(),
    )

    assert first["deliveries"][0]["severity"] == "warning"
    assert second["deliveries"][0]["severity"] == "warning"
    assert third["deliveries"][0]["severity"] == "critical"
    assert third["deliveries"][0]["payload"]["policy_escalation"]["applied"] is True
