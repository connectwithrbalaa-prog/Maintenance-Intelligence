import json

import pytest
from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app
from maintenance_intelligence.api import portal as portal_mod


READ_HEADERS = {"x-user-id": "viewer-1", "x-user-role": "viewer"}


@pytest.fixture(autouse=True)
def _enable_dev_headers(monkeypatch):
    monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")


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

    runs = client.get("/api/v1/portal/runs", headers=READ_HEADERS)
    assert runs.status_code == 200
    payload = runs.json()
    assert len(payload) == 1
    assert payload[0]["run_id"] == "RUN-123"
    assert payload[0]["title"] == "Replace bearing before next shift"
    assert payload[0]["context_meta"]["asset_id"] == "PUMP-101"

    detail = client.get("/api/v1/portal/runs/RUN-123", headers=READ_HEADERS)
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

    runs = client.get("/api/v1/portal/runs", headers=READ_HEADERS)
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

    detail = client.get("/api/v1/portal/runs/RUN-BAD", headers=READ_HEADERS)
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

    detail = client.get("/api/v1/portal/runs/RUN-PARTIAL", headers=READ_HEADERS)
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

    detail = client.get("/api/v1/portal/runs/%20RUN-123", headers=READ_HEADERS)
    assert detail.status_code == 400
    assert detail.json()["detail"] == "Invalid run id"


def test_portal_run_detail_includes_persisted_repair_plan_snapshot(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-PLAN.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-PLAN",
                "status": "ok",
                "recommendation_id": "REC-PLAN",
                "repair_plan_id": "RP-123",
                "structured": {
                    "title": "Replace bearing before next shift",
                    "summary": "Structured RCA proposed a repair plan.",
                    "repair_plan": {
                        "plan_id": "RP-123",
                        "procedure_steps": [
                            {"seq": 1, "action": "Isolate the pump", "safety_note": "Apply LOTO", "estimated_mins": 15},
                            {"seq": 2, "action": "Replace the bearing", "safety_note": "Verify lift points", "estimated_mins": 90},
                        ],
                        "tools_required": ["Torque wrench", "Laser alignment kit"],
                        "safety_requirements": ["LOTO required"],
                        "permit_type": "hot-work",
                        "estimated_duration_hrs": 4,
                        "spare_parts_cost_estimate": 1295,
                        "parts_list": [
                            {
                                "part_no": "BRG-9",
                                "description": "Bearing kit",
                                "qty": 1,
                                "lead_time_days": 2,
                            }
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))
    monkeypatch.setattr(
        portal_mod,
        "get_repair_plan",
        lambda dsn, plan_id: {
            "plan_id": plan_id,
            "run_id": "RUN-PLAN",
            "recommendation_id": "REC-PLAN",
            "org_id": "demo-org",
            "asset_id": "PUMP-101",
            "summary": "Replace the inboard bearing and re-align the shaft.",
            "rationale": "Repeated vibration and temperature spikes.",
            "confidence": 0.83,
            "status": "pending",
            "created_at": "2026-03-15T10:03:00Z",
            "updated_at": "2026-03-15T10:04:00Z",
        },
    )
    monkeypatch.setattr(
        portal_mod,
        "list_parts_for_plan",
        lambda dsn, plan_id: [
            {
                "part_id": "PART-1",
                "plan_id": plan_id,
                "name": "Bearing kit",
                "description": "OEM replacement set",
                "quantity": 1,
                "unit": "ea",
                "metadata": {"sku": "BRG-9"},
                "created_at": "2026-03-15T10:05:00Z",
            }
        ],
    )

    client = TestClient(app)

    detail = client.get("/api/v1/portal/runs/RUN-PLAN", headers=READ_HEADERS)
    assert detail.status_code == 200

    payload = detail.json()
    assert payload["repair_plan_id"] == "RP-123"
    assert payload["repair_plan"]["plan_id"] == "RP-123"
    assert payload["repair_plan"]["summary"] == "Replace the inboard bearing and re-align the shaft."
    assert payload["repair_plan"]["procedure_steps"] == [
        {"seq": 1.0, "action": "Isolate the pump", "safety_note": "Apply LOTO", "estimated_mins": 15.0},
        {"seq": 2.0, "action": "Replace the bearing", "safety_note": "Verify lift points", "estimated_mins": 90.0},
    ]
    assert payload["repair_plan"]["tools_required"] == ["Torque wrench", "Laser alignment kit"]
    assert payload["repair_plan"]["parts"][0]["name"] == "Bearing kit"
    assert payload["repair_plan"]["parts_list"][0]["part_no"] == "BRG-9"


def test_portal_run_detail_keeps_structured_repair_plan_when_lookup_fails(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-PLAN-FAIL.json").write_text(
        json.dumps(
            {
                "run_id": "RUN-PLAN-FAIL",
                "status": "warn",
                "repair_plan_id": "RP-FAIL",
                "structured": {
                    "repair_plan": {
                        "plan_id": "RP-FAIL",
                        "procedure_steps": [
                            {"seq": 1, "action": "Verify coupling alignment", "safety_note": "Check guards", "estimated_mins": 30}
                        ],
                        "parts_list": [
                            {
                                "part_no": "SEAL-42",
                                "description": "Seal kit",
                                "qty": 1,
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))
    monkeypatch.setattr(portal_mod, "get_repair_plan", lambda dsn, plan_id: (_ for _ in ()).throw(RuntimeError("db down")))

    client = TestClient(app)

    detail = client.get("/api/v1/portal/runs/RUN-PLAN-FAIL", headers=READ_HEADERS)

    assert detail.status_code == 200

    payload = detail.json()
    assert payload["repair_plan"]["plan_id"] == "RP-FAIL"
    assert payload["repair_plan"]["load_error"] == "Repair plan lookup unavailable"
    assert payload["repair_plan"]["procedure_steps"] == [
        {"seq": 1.0, "action": "Verify coupling alignment", "safety_note": "Check guards", "estimated_mins": 30.0}
    ]


def test_portal_run_endpoints_require_authenticated_identity(tmp_path, monkeypatch):
    run_dir = tmp_path / "portal-outs" / "2026-03-15"
    run_dir.mkdir(parents=True)
    (run_dir / "RUN-123.json").write_text(json.dumps({"run_id": "RUN-123", "structured": {}}), encoding="utf-8")
    monkeypatch.setenv("MI_RUN_SUMMARY_DIR", str(tmp_path / "portal-outs"))
    monkeypatch.delenv("MI_DEV_ALLOW_HEADERS", raising=False)

    client = TestClient(app)

    runs = client.get("/api/v1/portal/runs")
    detail = client.get("/api/v1/portal/runs/RUN-123")

    assert runs.status_code == 403
    assert runs.json()["detail"] == "Portal run data requires an authenticated identity"
    assert detail.status_code == 403
    assert detail.json()["detail"] == "Portal run data requires an authenticated identity"


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
    assert "Recommendation follow-through snapshot" in page.text
    assert "renderFollowThroughPanel" in page.text
    assert "Current proposal follow-through" in page.text
    assert "Work order completion" in page.text
    assert "Repair plan snapshot" in page.text
    assert "Persisted repair plan" in page.text
    assert "Repair plan record could not be loaded" in page.text
    assert "No persisted repair plan is linked to this run yet." in page.text
    assert "Run comparison" in page.text
    assert "Compare against" in page.text
    assert "Confidence drift" in page.text
    assert "Check confidence drift, feedback deltas, and action-set changes against another run." in page.text
    assert '${adminRetry ? "Admin retry" : "Retry"} the PM handoff for ${run.run_id}? ${retryState.attemptsRemaining} attempts remaining.' in page.text
    assert "Retry limit reached" in page.text
    assert "No approval attempt recorded for this run in this browser session." in page.text
    assert "Approve the PM proposal for" in page.text
    assert "Approval history" in page.text
    assert "No approval attempts recorded yet." in page.text
    assert "Audit history stays in the current run view." in page.text
    assert "Showing the in-app audit trail for ${escapeHtml(proposalId || \"this proposal\")}." in page.text
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
    assert "Showing ${escapeHtml(attempts.length)} of ${escapeHtml(history?.total_count ?? attempts.length)} attempts" in page.text
    assert "appendApprovalHistoryPage" in page.text
    assert "existingAttempts.concat" in page.text
    assert "history?page=${encodeURIComponent(page)}&size=${encodeURIComponent(size)}" in page.text
    assert "Attempt state" in page.text
    assert "Reused existing CMMS handoff result." in page.text
    assert "Fresh handoff result." in page.text
    assert "Last attempt:" in page.text
    assert "Attempt ${attemptNumber} of ${attemptCount}" in page.text
    assert "Retries remaining:" in page.text
    assert "Connector:" in page.text
    assert "Latest connector outcome" in page.text
    assert "Trace every approval and retry attempt without leaving the run view." in page.text
    assert "Handoff exceptions queue" in page.text
    assert "Surface PM proposals that need retry, escalation, or connector cleanup before handoff can finish." in page.text
    assert "Current proposal exception state" in page.text
    assert "Loading handoff exceptions" in page.text
    assert "Handoff exceptions unavailable" in page.text
    assert "No handoff exceptions right now" in page.text
    assert "There are no PM proposals waiting on retry, escalation, or connector cleanup right now." in page.text
    assert "Current proposal needs attention first" in page.text
    assert "More urgent handoffs exist" in page.text
    assert "Current proposal is clear" in page.text
    assert "Source /api/v1/agents/pm/proposals" in page.text
    assert "Current run proposal" in page.text
    assert "normalizeHandoffProposal" in page.text
    assert "describeHandoffException" in page.text
    assert "renderHandoffExceptionsPanel" in page.text
    assert "ensureHandoffExceptionsReport" in page.text
    assert "resetHandoffExceptionsReport" in page.text
    assert "submitHandoffQueueRetry" in page.text
    assert "Run admin retry" in page.text
    assert "Open follow-through" in page.text
    assert 'data-handoff-open-audit-run-id' in page.text
    assert "Open audit trail" in page.text
    assert "Audit history stays in the current run view." in page.text
    assert "Queue view" in page.text
    assert "Sort order" in page.text
    assert "Handoff queue view" in page.text
    assert "Handoff queue sort" in page.text
    assert "Handoff queue rows shown" in page.text
    assert "Rows shown" in page.text
    assert "Top 3" in page.text
    assert "Top 6" in page.text
    assert "Top 10" in page.text
    assert "Showing top ${escapeHtml(state.handoffExceptions.limit)}" in page.text
    assert "All exceptions" in page.text
    assert "Admin retries only" in page.text
    assert "Connector failures only" in page.text
    assert "Retry limits only" in page.text
    assert "Oldest waiting first" in page.text
    assert "No exceptions in this filter" in page.text
    assert "Filtered out" in page.text
    assert "Connector failures" in page.text
    assert "View ${escapeHtml(handoffViewLabel(state.handoffExceptions.view))}" in page.text
    assert "Age ${escapeHtml(formatMinutesAsDuration(row.ageMinutes))}" in page.text
    assert "handoffRowMatchesView" in page.text
    assert "handoffRowsForDisplay" in page.text
    assert "handoffViewLabel" in page.text
    assert "handoffViewSelect" in page.text
    assert "handoffSortSelect" in page.text
    assert "miPortalHandoffPrefs:" in page.text
    assert "readHandoffQueuePreferences" in page.text
    assert "writeHandoffQueuePreferences" in page.text
    assert "applyHandoffQueuePreferences" in page.text
    assert "handoffQueuePreferencesStorageKey" in page.text
    assert "normalizeHandoffQueueView" in page.text
    assert "normalizeHandoffQueueSort" in page.text
    assert "normalizeHandoffQueueAgeBucket" in page.text
    assert "normalizeHandoffQueueLimit" in page.text
    assert "handoffAgeBucketLabel" in page.text
    assert "handoffRowMatchesAgeBucket" in page.text
    assert "Handoff queue age filters" in page.text
    assert "data-handoff-age-bucket" in page.text
    assert "Age filter ${escapeHtml(handoffAgeBucketLabel(state.handoffExceptions.ageBucket))}" in page.text
    assert "Sort ${escapeHtml(handoffSortLabel(state.handoffExceptions.sort))}" in page.text
    assert "Retries remaining ${escapeHtml(retriesRemaining)}" in page.text
    assert "Longest wait ${escapeHtml(longestWait)}" in page.text
    assert "Visible classes ${escapeHtml(visibleClasses)}" in page.text
    assert "Aging risk ${escapeHtml(agingRiskCount)}" in page.text
    assert "Lead age ${escapeHtml(leadAgeLabel)}" in page.text
    assert "Current rank ${escapeHtml(currentRankLabel)}" in page.text
    assert "handoffSortLabel" in page.text
    assert "handoffRetriesRemaining" in page.text
    assert "handoffLongestWait" in page.text
    assert "handoffVisibleClasses" in page.text
    assert "handoffAgingRiskCount" in page.text
    assert "handoffLeadAgeLabel" in page.text
    assert "handoffCurrentRankLabel" in page.text
    assert "No connector failures in this filter" in page.text
    assert "No proposals currently show connector-failure handoffs in this view." in page.text
    assert "No admin retries waiting" in page.text
    assert "No proposals are currently waiting on an admin retry in this view." in page.text
    assert "No retry limits hit" in page.text
    assert "No proposals have exhausted their retry limit in this view." in page.text
    assert "No aging risk or SLA watch items" in page.text
    assert "No proposals in this view currently exceed the SLA watch threshold." in page.text
    assert "Priority first" in page.text
    assert "Oldest first" in page.text
    assert "Reset to defaults" in page.text
    assert "Reset handoff queue preferences" in page.text
    assert "handoffPreferencesResetButton" in page.text
    assert "Admin role required for retry." in page.text
    assert "data-handoff-retry-proposal-id" in page.text
    assert "data-handoff-focus-run-id" in page.text
    assert 'state.handoffExceptions.report = await fetchJson("/api/v1/agents/pm/proposals", {' in page.text
    assert "headers: portalIdentityHeaders()" in page.text
    assert "Live evidence" in page.text
    assert "Recent signals and rollups for the asset tied to this RCA run." in page.text
    assert "No asset evidence link yet" in page.text
    assert "This run does not include an asset_id, so live signals cannot be fetched." in page.text
    assert "Loading live evidence" in page.text
    assert "Evidence unavailable" in page.text
    assert "No live signal evidence yet" in page.text
    assert "This asset does not have recent signals or rollups available right now." in page.text
    assert "Recent signals" in page.text
    assert "Rollup summary" in page.text
    assert "No recent signals were returned for this asset." in page.text
    assert "No rollups were returned for this asset." in page.text
    assert "Trend steady" in page.text
    assert "Trend rising" in page.text
    assert "Trend easing" in page.text
    assert "compareEvidenceValues" in page.text
    assert "latestEvidenceTrend" in page.text
    assert "rollupEvidenceTrend" in page.text
    assert "renderEvidenceTrendChip" in page.text
    assert "Signal ${escapeHtml(signal.signal_id || 'unlabeled')} · Source /api/v1/signals/summary?asset_id=${encodeURIComponent(assetId)}&limit=6" in page.text
    assert "renderEvidencePanel" in page.text
    assert "loadEvidenceSummary" in page.text
    assert "evidenceByAssetId" in page.text
    assert "evidenceLoadingByAssetId" in page.text
    assert "evidenceErrorByAssetId" in page.text
    assert "/api/v1/signals/summary?asset_id=${encodeURIComponent(assetId)}&limit=6" in page.text
    assert "Asset triage queue" in page.text
    assert "Rank nearby bad actors so operators can pull the highest-pressure assets forward first." in page.text
    assert "Current asset queue rank" in page.text
    assert "Loading triage queue" in page.text
    assert "Triage queue unavailable" in page.text
    assert "No triage pressure yet" in page.text
    assert "There are no ranked assets in the current bad-actor window yet. The queue will populate as events and work orders accumulate." in page.text
    assert "Current asset leads the queue" in page.text
    assert "Higher-pressure assets exist" in page.text
    assert "Current asset is outside the top queue" in page.text
    assert "Source /api/v1/reports/bad-actors" in page.text
    assert "Current run asset" in page.text
    assert "triageCurrentAssetRow" in page.text
    assert "renderTriagePanel" in page.text
    assert "ensureTriageReport" in page.text
    assert "resetTriageReport" in page.text
    assert 'state.triage.report = await fetchJson(`/api/v1/reports/bad-actors?limit=${encodeURIComponent(state.triage.limit)}`, {' in page.text
    assert "headers: portalIdentityHeaders()" in page.text
    assert "/api/v1/reports/bad-actors?limit=${encodeURIComponent(state.triage.limit)}" in page.text
    assert "Asset trend snapshot" in page.text
    assert "Compact outcomes view for demos in the portal." in page.text
    assert "outcomesScopeSelect" in page.text
    assert "Select analytics scope" in page.text
    assert "outcomesEntitySelect" in page.text
    assert "Select asset trend series" in page.text
    assert "Select operator trend series" in page.text
    assert "Select org trend series" in page.text
    assert "Scope" in page.text
    assert "Entity" in page.text
    assert "Asset selector" in page.text
    assert "Operator selector" in page.text
    assert "Org selector" in page.text
    assert "Source outcomes.asset_metrics" in page.text
    assert "Source outcomes.user_metrics" in page.text
    assert "Source outcomes.org_metrics" in page.text
    assert "selectedOutcomeScopeByRunId" in page.text
    assert "selectedOutcomeUserByRunId" in page.text
    assert "selectedOutcomeOrgByRunId" in page.text
    assert "outcomesPrimaryKpiLabel" in page.text
    assert "outcomesPrimaryKpiValue" in page.text
    assert "Scope ${escapeHtml(config.label)}" in page.text
    assert "Current ${escapeHtml(selectedEntityId)}" in page.text
    assert "selectedTotalMetric" in page.text
    assert "totalLabel" in page.text
    assert "Top contributor" in page.text
    assert "Top volume" in page.text
    assert "Last ${escapeHtml(outcomesWindow)} days" in page.text
    assert "renderOutcomesPanel" in page.text
    assert "ensureOutcomesReport" in page.text
    assert "resetOutcomesReport" in page.text
    assert 'state.outcomes.report = await fetchJson(`/api/v1/reports/rca-outcomes?window=${encodeURIComponent(state.outcomes.windowDays)}`, {' in page.text
    assert "Switch between asset, operator, and org lenses without leaving the run view." in page.text
    assert "Start with the asset tied to this run, or compare another asset that already has live trend data." in page.text
    assert "Follow the signed-in operator first, or switch to another operator with recorded feedback activity." in page.text
    assert "Start with the current organization, or compare another org that already has live feedback activity." in page.text
    assert "No live trends yet" in page.text
    assert "There are no asset, operator, or organization trend lines for this outcomes window yet. The panel will fill in as work orders and feedback arrive." in page.text
    assert "No operator trends yet" in page.text
    assert "No organization trends yet" in page.text
    assert "Loading outcomes" in page.text
    assert "Pulling the last" in page.text
    assert "Outcomes unavailable" in page.text
    assert "We could not load outcomes trends right now:" in page.text
    assert "Partial report" in page.text
    assert "Showing the nearest live series" in page.text
    assert 'renderOutcomesNote("Info", "Showing the nearest live series", config.fallbackMessage(expectedEntityId, selectedEntityId))' in page.text
    assert "This view defaults to operator ${escapeHtml(expectedId)}, but this window only has trend lines for ${escapeHtml(selectedId)}. You are looking at the closest live operator instead." in page.text
    assert "This view defaults to organization ${escapeHtml(expectedId)}, but this window only has trend lines for ${escapeHtml(selectedId)}. You are looking at the closest live organization instead." in page.text
    assert "Workorder volume" in page.text
    assert "Feedback volume" in page.text
    assert "Acceptance rate" in page.text
    assert "Decision quality across the last ${outcomesWindow} days." in page.text
    assert "Waiting" in page.text
    assert "Peak daily volume" in page.text
    assert "Range ${formatTrendValue(low, metricName, options)} to ${formatTrendValue(peak, metricName, options)} across the current window." in page.text
    assert "No accept or reject feedback was recorded for this asset in the current window." in page.text
    assert "No work orders were recorded for this asset in the current window." in page.text
    assert "No feedback was recorded for this operator in the current window." in page.text
    assert "No accept or reject decisions were recorded for this operator in the current window." in page.text
    assert "No feedback was recorded for this organization in the current window." in page.text
    assert "No accept or reject decisions were recorded for this organization in the current window." in page.text
    assert "No acceptance decisions yet" in page.text
    assert "No work order volume yet" in page.text
    assert "No feedback yet" in page.text
    assert "chart-line" in page.text
    assert "chart-dot" in page.text
    assert "buildTrendSegments" in page.text
    assert "/api/v1/reports/rca-outcomes?window=${encodeURIComponent(state.outcomes.windowDays)}" in page.text


def test_portal_index_includes_feedback_loop_controls():
    client = TestClient(app)

    page = client.get("/portal")
    assert page.status_code == 200
    assert "Feedback loop" in page.text
    assert "Submit operator feedback to improve future RCA runs." in page.text
    assert "Feedback decision" in page.text
    assert "Reason or field note" in page.text
    assert "Edited title (optional)" in page.text
    assert "Edited immediate actions (optional)" in page.text
    assert "Submit feedback" in page.text
    assert "Saving feedback..." in page.text
    assert "Feedback is submitted as" in page.text
    assert "No operator feedback recorded yet for this run." in page.text
    assert "Loading feedback history..." in page.text
    assert "Unable to load feedback history:" in page.text
    assert 'Accept ${escapeHtml(counts.accept || 0)}' in page.text
    assert 'Reject ${escapeHtml(counts.reject || 0)}' in page.text
    assert 'Edited ${escapeHtml(counts.edited || 0)}' in page.text
    assert "loadFeedbackHistory" in page.text
    assert "submitFeedback" in page.text
    assert "feedbackByRunId" in page.text
    assert "feedbackDraftByRunId" in page.text
    assert "feedbackSubmittingByRunId" in page.text
    assert "/api/v1/rca/feedback?run_id=${encodeURIComponent(run.run_id)}&limit=12" in page.text
    assert 'await postJson("/api/v1/rca/feedback"' in page.text