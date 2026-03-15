import json

from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app


def test_portal_routes_with_run_summaries(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    run_path = run_dir / "RUN-123.json"
    run_path.write_text(
        json.dumps(
            {
                "run_id": "RUN-123",
                "status": "ok",
                "event_id": "EV-9",
                "recommendation_id": "REC-44",
                "structured": {
                    "title": "Replace bearing before next shift",
                    "confidence": 0.83,
                    "hypothesis": ["Bearing wear is increasing vibration"],
                    "immediate_actions": ["Inspect lubrication"],
                    "pm_suggestions": ["Schedule bearing replacement"],
                },
                "model": {
                    "name": "gpt-4.1",
                    "version": "test",
                    "latency_ms": 812,
                    "confidence": 0.83,
                },
                "context_meta": {
                    "asset_id": "PUMP-101",
                    "event_kind": "anomaly",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))

    client = TestClient(app)

    page = client.get("/portal")
    assert page.status_code == 200
    assert "Maintenance Intelligence Portal" in page.text

    runs = client.get("/api/v1/portal/runs")
    assert runs.status_code == 200
    payload = runs.json()
    assert len(payload) == 1
    assert payload[0]["run_id"] == "RUN-123"
    assert payload[0]["title"] == "Replace bearing before next shift"
    assert payload[0]["context_meta"]["asset_id"] == "PUMP-101"

    detail = client.get("/api/v1/portal/runs/RUN-123")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["structured"]["hypothesis"] == ["Bearing wear is increasing vibration"]
    assert detail_payload["model"]["latency_ms"] == 812


def test_portal_skips_invalid_json_and_coerces_malformed_nested_fields(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-BAD.json").write_text("{not valid json", encoding="utf-8")
    (run_dir / "RUN-ODD.json").write_text(
        json.dumps(
            {
                "run_id": 987,
                "status": ["broken"],
                "event_id": 55,
                "recommendation_id": True,
                "structured": ["not-a-dict"],
                "model": "bad-model",
                "context_meta": "not-a-dict",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))

    client = TestClient(app)

    runs = client.get("/api/v1/portal/runs")
    assert runs.status_code == 200
    payload = runs.json()
    assert len(payload) == 1
    assert payload[0]["run_id"] == "987"
    assert payload[0]["status"] == "unknown"
    assert payload[0]["event_id"] == "55"
    assert payload[0]["recommendation_id"] is None
    assert payload[0]["title"] is None
    assert payload[0]["hypothesis"] == []
    assert payload[0]["context_meta"] == {}


def test_portal_run_detail_returns_422_for_malformed_summary_file(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-BAD.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))

    client = TestClient(app)

    detail = client.get("/api/v1/portal/runs/RUN-BAD")
    assert detail.status_code == 422
    assert detail.json()["detail"] == "Run summary is malformed"