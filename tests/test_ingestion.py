import json

from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.runner.edge_agent import EdgeEventBuffer
from maintenance_intelligence.runner.edge_command_buffer import EdgeCommandBuffer
from maintenance_intelligence.services import ingestion as ingestion_mod
from maintenance_intelligence.services import notifications as notifications_mod


def _event(event_id: str, org_id: str = "demo-org") -> dict:
    return {
        "event_id": event_id,
        "occurred_at": "2026-03-15T10:00:00Z",
        "org_id": org_id,
        "asset_id": "PUMP-101",
        "kind": "anomaly",
        "severity": "high",
        "summary": f"Event {event_id}",
        "details": {"source": "edge"},
        "lineage": {"channel": "kafka"},
    }


def test_connect_edge_central_failure_emits_runtime_notification(tmp_path, monkeypatch):
    buffer_path = tmp_path / "edge" / "edge.sqlite3"
    command_buffer_path = tmp_path / "edge" / "edge-command.sqlite3"
    monkeypatch.setenv("MI_EDGE_BUFFER_PATH", str(buffer_path))
    monkeypatch.setenv("MI_EDGE_COMMAND_BUFFER_PATH", str(command_buffer_path))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            {
                "default": {
                    "webhook_url": "https://hooks.example.test/edge",
                    "minimum_severity": "warning",
                }
            }
        ),
    )
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    deliveries = []

    def fake_send(url, payload, timeout_s):
        deliveries.append({"url": url, "payload": payload, "timeout_s": timeout_s})
        return True, 202, ""

    monkeypatch.setattr(notifications_mod, "_send_webhook", fake_send)
    monkeypatch.setattr(ingestion_mod, "emit_notification", notifications_mod.emit_notification)
    monkeypatch.setattr(
        ingestion_mod,
        "open_central_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("central store unavailable")),
    )

    buffer = EdgeEventBuffer(str(buffer_path), max_events=10)
    buffer.buffer_event(_event("EV-1"), error="central store unavailable")
    command_queue = EdgeCommandBuffer(str(command_buffer_path))
    command_queue.enqueue_command("REC-1", {"proposal_id": "REC-1"}, error="cmms offline")

    conn = ingestion_mod._connect_edge_central("dsn", Settings(), buffer)

    assert conn is None
    assert len(deliveries) == 1
    assert deliveries[0]["payload"]["event_type"] == "edge.degraded"
    assert deliveries[0]["payload"]["payload"]["queued_command_count"] == 1


def test_emit_edge_connectivity_notification_uses_buffered_org_context(tmp_path, monkeypatch):
    buffer_path = tmp_path / "edge" / "edge.sqlite3"
    command_buffer_path = tmp_path / "edge" / "edge-command.sqlite3"
    monkeypatch.setenv("MI_EDGE_BUFFER_PATH", str(buffer_path))
    monkeypatch.setenv("MI_EDGE_COMMAND_BUFFER_PATH", str(command_buffer_path))
    monkeypatch.setenv(
        "MI_NOTIFICATION_WEBHOOK_ROUTES",
        json.dumps(
            {
                "demo-org": {
                    "webhook_url": "https://hooks.example.test/demo-org",
                    "minimum_severity": "warning",
                }
            }
        ),
    )
    monkeypatch.setenv("MI_NOTIFICATION_LOG_PATH", str(tmp_path / "notifications.jsonl"))
    deliveries = []

    def fake_send(url, payload, timeout_s):
        deliveries.append({"url": url, "payload": payload, "timeout_s": timeout_s})
        return True, 202, ""

    monkeypatch.setattr(notifications_mod, "_send_webhook", fake_send)
    monkeypatch.setattr(ingestion_mod, "emit_notification", notifications_mod.emit_notification)

    buffer = EdgeEventBuffer(str(buffer_path), max_events=10)
    buffer.buffer_event(_event("EV-1", org_id="demo-org"), error="central store unavailable")

    ingestion_mod._emit_edge_connectivity_notification(Settings(), buffer)

    assert len(deliveries) == 1
    assert deliveries[0]["url"] == "https://hooks.example.test/demo-org"
    assert deliveries[0]["payload"]["org_id"] == "demo-org"
