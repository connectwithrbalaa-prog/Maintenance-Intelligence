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
    assert detail_payload["structured"]["summary"] == ""


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
    assert payload[0]["recommendation_id"] == ""
    assert payload[0]["title"] == ""
    assert payload[0]["summary"] == ""
    assert payload[0]["hypothesis"] == []
    assert payload[0]["context_meta"] == {}
    assert payload[0]["model"] == {"name": "", "version": "", "latency_ms": None, "confidence": None}


def test_portal_run_detail_returns_422_for_malformed_summary_file(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-BAD.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))

    client = TestClient(app)

    detail = client.get("/api/v1/portal/runs/RUN-BAD")
    assert detail.status_code == 422
    assert detail.json()["detail"] == "Run summary is malformed"


def test_portal_run_detail_sanitizes_partial_payload_and_keeps_predictable_shape(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-PARTIAL.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-PARTIAL",
                "status": "partial",
                "structured": {
                    "summary": ["bad-summary"],
                    "hypothesis": [1, "Bearing wear", None, False],
                    "immediate_actions": "inspect now",
                    "pm_suggestions": ["Schedule inspection", 77],
                },
                "model": {"latency_ms": "fast", "confidence": 0.42},
                "context_meta": {
                    "asset_id": ["PUMP-9"],
                    "event_kind": "anomaly",
                    "doc_chunk_ids": ["DOC-1", 22],
                    "nested": {"score": 3, "ignore": None},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))

    client = TestClient(app)

    detail = client.get("/api/v1/portal/runs/RUN-PARTIAL")
    assert detail.status_code == 200

    payload = detail.json()
    assert payload["run_id"] == "RUN-PARTIAL"
    assert payload["status"] == "partial"
    assert payload["title"] == ""
    assert payload["summary"] == ""
    assert payload["event_id"] == ""
    assert payload["recommendation_id"] == ""
    assert payload["hypothesis"] == ["1", "Bearing wear"]
    assert payload["immediate_actions"] == []
    assert payload["pm_suggestions"] == ["Schedule inspection", "77"]
    assert payload["structured"] == {
        "title": "",
        "summary": "",
        "confidence": None,
        "hypothesis": ["1", "Bearing wear"],
        "immediate_actions": [],
        "pm_suggestions": ["Schedule inspection", "77"],
    }
    assert payload["model"] == {
        "name": "",
        "version": "",
        "latency_ms": None,
        "confidence": 0.42,
    }
    assert payload["context_meta"] == {
        "asset_id": ["PUMP-9"],
        "event_kind": "anomaly",
        "doc_chunk_ids": ["DOC-1", "22"],
        "nested": {"score": "3"},
    }


def test_portal_run_detail_rejects_invalid_run_id(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))

    client = TestClient(app)

    detail = client.get("/api/v1/portal/runs/%20RUN-123")
    assert detail.status_code == 400
    assert detail.json()["detail"] == "Invalid run id"


def test_portal_index_includes_safe_detail_messages_for_partial_runs():
    client = TestClient(app)

    page = client.get("/portal")
    assert page.status_code == 200
    assert "Current identity" in page.text
    assert "Role badge refreshes from whoami when available." in page.text
    assert "Apply demo identity" in page.text
    assert "miPortalOrgId" in page.text
    assert "miPortalDevMode" in page.text
    assert "/api/v1/whoami" in page.text
    assert "identityBadgeText" in page.text
    assert "renderIdentityPanel" in page.text
    assert "refreshIdentity" in page.text
    assert "Operator" in page.text
    assert "Maintainer" in page.text
    assert "Admin" in page.text
    assert "No hypotheses were stored for this run." in page.text
    assert "Missing fields were left empty so the detail view can still load safely." in page.text
    assert "Portal request failed" in page.text
    assert "Approve PM proposal" in page.text
    assert "Role planner" in page.text
    assert "Org demo-org" in page.text
    assert "Admin Retry" in page.text
    assert "Admin Retry Only" in page.text
    assert "Admin retry in progress..." in page.text
    assert "Manual retries require an admin or maintainer role." in page.text
    assert "miPortalUserRole" in page.text
    assert "admin_retry" in page.text
    assert "Admin retry attempts remaining:" in page.text
    assert "Retrying handoff..." in page.text
    assert '${adminRetry ? "Admin retry" : "Retry"} the PM handoff for ${run.run_id}? ${retryState.attemptsRemaining} attempts remaining.' in page.text
    assert "Retry limit reached" in page.text
    assert "No approval attempt recorded for this run in this browser session." in page.text
    assert "Approve the PM proposal for" in page.text
    assert "Approval history" in page.text
    assert "No approval attempts recorded yet." in page.text
    assert "View full audit" in page.text
    assert "audit-item" in page.text
    assert "admin-origin" in page.text
    assert "audit-head" in page.text
    assert "audit-badge actor" in page.text
    assert "Origin ${escapeHtml(attempt.origin || \"approval\")}" in page.text
    assert "Actor ${escapeHtml(attempt.approved_by || \"Unknown approver\")}" in page.text
    assert "origin-admin" in page.text
    assert "origin-approval" in page.text
    assert "Load more" in page.text
    assert "Loading more audit..." in page.text
    assert "All recorded audit attempts are visible." in page.text
    assert "Showing ${escapeHtml(attempts.length)} of ${escapeHtml(history?.total_count ?? attempts.length)} attempts." in page.text
    assert "appendApprovalHistoryPage" in page.text
    assert "existingAttempts.concat" in page.text
    assert "history?page=${encodeURIComponent(page)}&size=${encodeURIComponent(size)}" in page.text
    assert "Attempt state:" in page.text
    assert "Reused existing CMMS handoff result." in page.text
    assert "Fresh handoff result." in page.text
    assert "Last attempt:" in page.text
    assert "Attempt ${attemptNumber} of ${attemptCount}" in page.text
    assert "Retries remaining:" in page.text
    assert "Connector:" in page.text