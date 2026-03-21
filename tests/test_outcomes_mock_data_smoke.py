import json
import os
import subprocess
import sys

import psycopg2
import pytest
from fastapi.testclient import TestClient

from maintenance_intelligence.api.main import app

testcontainers_postgres = pytest.importorskip("testcontainers.postgres")
PostgresContainer = testcontainers_postgres.PostgresContainer


def _docker_available() -> bool:
    result = subprocess.run(
        ["docker", "info"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode == 0


@pytest.mark.skipif(not _docker_available(), reason="Docker daemon is not available")
def test_outcomes_report_with_mock_data_on_ephemeral_postgres(monkeypatch) -> None:
    db_name = "maintenance"
    db_user = "postgres"
    db_password = "postgres"

    with PostgresContainer(
        "pgvector/pgvector:pg15",
        dbname=db_name,
        username=db_user,
        password=db_password,
    ) as postgres:
        host = postgres.get_container_host_ip()
        port = str(postgres.get_exposed_port(5432))
        env = os.environ.copy()
        env.update(
            {
                "POSTGRES_DB": db_name,
                "POSTGRES_USER": db_user,
                "POSTGRES_PASSWORD": db_password,
                "POSTGRES_HOST": host,
                "POSTGRES_PORT": port,
                "MI_POSTGRES_HOST": host,
                "MI_POSTGRES_DB": db_name,
                "MI_POSTGRES_USER": db_user,
                "MI_POSTGRES_PASSWORD": db_password,
                "MI_POSTGRES_PORT": port,
            }
        )

        result = subprocess.run(
            [sys.executable, "-m", "maintenance_intelligence.db.migrate"],
            cwd=os.getcwd(),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        for key, value in env.items():
            if key.startswith("POSTGRES_") or key.startswith("MI_POSTGRES_"):
                monkeypatch.setenv(key, value)

        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=host,
            port=port,
        )
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO events (event_id, occurred_at, org_id, asset_id, kind, severity, summary, details, lineage)
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb),
                            (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb),
                            (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                        """,
                        (
                            "EVT-1",
                            "2026-03-14T08:00:00Z",
                            "demo-org",
                            "PUMP-101",
                            "alarm",
                            "high",
                            "High vibration",
                            json.dumps({"rms": 8.5}),
                            json.dumps({"source": "smoke"}),
                            "EVT-2",
                            "2026-03-15T08:00:00Z",
                            "demo-org",
                            "PUMP-101",
                            "alarm",
                            "high",
                            "High vibration persisted",
                            json.dumps({"rms": 8.9}),
                            json.dumps({"source": "smoke"}),
                            "EVT-3",
                            "2026-03-15T10:30:00Z",
                            "demo-org",
                            "PUMP-202",
                            "alarm",
                            "medium",
                            "Temperature alert",
                            json.dumps({"temp": 91}),
                            json.dumps({"source": "smoke"}),
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO workorders (
                            wo_id, asset_id, status, title, description, priority, metadata,
                            workorder_created_at, handoff_completed_at, workorder_completed_at
                        )
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s),
                            (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                        """,
                        (
                            "WO-1",
                            "PUMP-101",
                            "COMP",
                            "Inspect pump seal",
                            "Seal wear suspected",
                            "HIGH",
                            json.dumps(
                                {"evidence_event_id": "EVT-1", "handoff": {"backend": "maximo"}}
                            ),
                            "2026-03-14T10:00:00Z",
                            "2026-03-14T10:05:00Z",
                            "2026-03-14T13:00:00Z",
                            "WO-2",
                            "PUMP-101",
                            "DONE",
                            "Replace coupling",
                            "Coupling wear confirmed",
                            "MEDIUM",
                            json.dumps(
                                {"evidence_event_id": "EVT-2", "handoff": {"backend": "mock"}}
                            ),
                            "2026-03-15T10:00:00Z",
                            "2026-03-15T10:03:00Z",
                            "2026-03-15T14:00:00Z",
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO pm_proposals (
                            proposal_id, run_id, recommendation_id, event_id, asset_id, title, rationale,
                            confidence, status, source_file, proposed_by, approved_by, work_order_id, metadata
                        )
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb),
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb),
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb),
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            "REC-1",
                            "RUN-1",
                            "REC-1",
                            "EVT-1",
                            "PUMP-101",
                            "Inspect pump seal",
                            "Seal wear suspected",
                            0.91,
                            "approved",
                            "RUN-1.json",
                            "planner-1",
                            "planner-1",
                            "WO-1",
                            json.dumps(
                                {
                                    "approval": {
                                        "approved_at": "2026-03-14T09:55:00Z",
                                        "handoff_state": "success",
                                    },
                                    "approval_attempts": [
                                        {
                                            "attempted_at": "2026-03-14T09:55:00Z",
                                            "handoff_state": "success",
                                        }
                                    ],
                                }
                            ),
                            "REC-2",
                            "RUN-2",
                            "REC-2",
                            "EVT-2",
                            "PUMP-101",
                            "Replace coupling",
                            "Coupling wear confirmed",
                            0.86,
                            "approved",
                            "RUN-2.json",
                            "planner-2",
                            "planner-2",
                            "WO-2",
                            json.dumps(
                                {
                                    "approval": {
                                        "approved_at": "2026-03-15T09:58:00Z",
                                        "handoff_state": "success",
                                    },
                                    "approval_attempts": [
                                        {
                                            "attempted_at": "2026-03-15T09:58:00Z",
                                            "handoff_state": "success",
                                        }
                                    ],
                                }
                            ),
                            "REC-3",
                            "RUN-3",
                            "REC-3",
                            "EVT-3",
                            "PUMP-202",
                            "Inspect motor temp",
                            "Temperature alert",
                            0.74,
                            "pending",
                            "RUN-3.json",
                            "planner-3",
                            "planner-3",
                            None,
                            json.dumps(
                                {
                                    "approval": {
                                        "attempted_at": "2026-03-15T11:30:00Z",
                                        "handoff_state": "failure",
                                    },
                                    "approval_attempts": [
                                        {
                                            "attempted_at": "2026-03-15T11:30:00Z",
                                            "handoff_state": "failure",
                                        }
                                    ],
                                }
                            ),
                            "REC-4",
                            "RUN-4",
                            "REC-4",
                            "EVT-3",
                            "PUMP-202",
                            "Retry connector push",
                            "Connector queue pending",
                            0.68,
                            "pending",
                            "RUN-4.json",
                            "planner-4",
                            "planner-4",
                            None,
                            json.dumps(
                                {
                                    "approval": {
                                        "attempted_at": "2026-03-15T11:00:00Z",
                                        "handoff_state": "pending",
                                    },
                                    "approval_attempts": [
                                        {
                                            "attempted_at": "2026-03-15T10:20:00Z",
                                            "handoff_state": "pending",
                                        },
                                        {
                                            "attempted_at": "2026-03-15T10:40:00Z",
                                            "handoff_state": "failure",
                                        },
                                        {
                                            "attempted_at": "2026-03-15T11:00:00Z",
                                            "handoff_state": "pending",
                                        },
                                    ],
                                }
                            ),
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO rca_feedback (id, run_id, recommendation_id, org_id, asset_id, action, changes, reason, user_id, created_at)
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s),
                            (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s),
                            (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                        """,
                        (
                            "FB-1",
                            "RUN-1",
                            "REC-1",
                            "demo-org",
                            "PUMP-101",
                            "accept",
                            json.dumps({}),
                            "good recommendation",
                            "operator-1",
                            "2026-03-14T12:00:00Z",
                            "FB-2",
                            "RUN-2",
                            "REC-2",
                            "demo-org",
                            "PUMP-101",
                            "reject",
                            json.dumps({}),
                            "not needed",
                            "operator-2",
                            "2026-03-15T12:00:00Z",
                            "FB-3",
                            "RUN-3",
                            "REC-3",
                            "demo-org",
                            "PUMP-101",
                            "accept",
                            json.dumps({}),
                            "completed",
                            "operator-3",
                            "2026-03-15T13:00:00Z",
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO signal_rollups (
                            rollup_id, asset_id, signal_type, period, start_time, end_time,
                            mean_value, min_value, max_value, count, anomaly_flags
                        )
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb),
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb),
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            "ROLLUP-1",
                            "PUMP-101",
                            "vibration",
                            "1h",
                            "2026-03-15T09:00:00Z",
                            "2026-03-15T10:00:00Z",
                            9.1,
                            8.5,
                            10.3,
                            12,
                            json.dumps({"high_vibration": True}),
                            "ROLLUP-2",
                            "PUMP-202",
                            "temperature",
                            "6h",
                            "2026-03-15T05:00:00Z",
                            "2026-03-15T11:00:00Z",
                            87.0,
                            83.0,
                            91.0,
                            8,
                            json.dumps({"high_temperature": True}),
                            "ROLLUP-3",
                            "PUMP-202",
                            "temperature",
                            "24h",
                            "2026-03-14T11:00:00Z",
                            "2026-03-15T11:00:00Z",
                            84.0,
                            79.0,
                            86.0,
                            24,
                            json.dumps({"high_temperature": True}),
                        ),
                    )

            monkeypatch.setenv("MI_DEV_ALLOW_HEADERS", "true")
            headers = {"x-user-id": "viewer-1", "x-user-role": "viewer"}
            client = TestClient(app)
            response = client.get("/api/v1/reports/rca-outcomes?window=30", headers=headers)
            assert response.status_code == 200
            payload = response.json()

            assert payload["status"] == "ok"
            assert payload["feedback_counts"] == {"accept": 2, "reject": 1, "edited": 0}
            assert payload["feedback_total"] == 3
            assert payload["acceptance_rate"] == pytest.approx(2 / 3)
            assert payload["ttr_seconds_avg"] == pytest.approx(7200.0)
            assert payload["mtbf_seconds_avg"] == pytest.approx(86400.0)
            assert payload["mttr_seconds_avg"] == pytest.approx(12600.0)
            assert payload["cmms_summary"] == {
                "success_total": 2,
                "pending_total": 1,
                "failure_total": 1,
                "admin_retry_required_total": 2,
                "limit_reached_total": 1,
                "approval_to_handoff_seconds_avg": pytest.approx(450.0),
            }
            assert payload["cmms_breakdowns"] == {
                "by_asset": {
                    "PUMP-101": {
                        "success_total": 2,
                        "pending_total": 0,
                        "failure_total": 0,
                        "admin_retry_required_total": 0,
                        "limit_reached_total": 0,
                        "approval_to_handoff_seconds_avg": pytest.approx(450.0),
                    },
                    "PUMP-202": {
                        "success_total": 0,
                        "pending_total": 1,
                        "failure_total": 1,
                        "admin_retry_required_total": 2,
                        "limit_reached_total": 1,
                        "approval_to_handoff_seconds_avg": None,
                    },
                },
                "by_backend": {
                    "maximo": {
                        "success_total": 1,
                        "pending_total": 0,
                        "failure_total": 0,
                        "admin_retry_required_total": 0,
                        "limit_reached_total": 0,
                        "approval_to_handoff_seconds_avg": pytest.approx(600.0),
                    },
                    "mock": {
                        "success_total": 1,
                        "pending_total": 0,
                        "failure_total": 0,
                        "admin_retry_required_total": 0,
                        "limit_reached_total": 0,
                        "approval_to_handoff_seconds_avg": pytest.approx(300.0),
                    },
                    "unknown": {
                        "success_total": 0,
                        "pending_total": 1,
                        "failure_total": 1,
                        "admin_retry_required_total": 2,
                        "limit_reached_total": 1,
                        "approval_to_handoff_seconds_avg": None,
                    },
                },
            }
            assert payload["top_assets_by_wo_volume"] == [{"asset_id": "PUMP-101", "count": 2}]
            assert payload["top_backends_by_handoff_volume"] == [
                {"backend": "unknown", "count": 2},
                {"backend": "maximo", "count": 1},
                {"backend": "mock", "count": 1},
            ]
            assert payload["early_warning_summary"]["total_assets"] == 2
            assert payload["early_warning_summary"]["status_counts"]["elevated"] >= 1
            assert payload["early_warning_summary"]["top_assets"][0]["asset_id"] in {
                "PUMP-101",
                "PUMP-202",
            }
            assert payload["top_users_by_feedback"] == [
                {"user_id": "operator-1", "count": 1},
                {"user_id": "operator-2", "count": 1},
                {"user_id": "operator-3", "count": 1},
            ]
            assert payload["top_orgs_by_feedback"] == [{"org_id": "demo-org", "count": 3}]
            assert payload["placeholders"] == {}
            assert sorted(payload["asset_metrics"].keys()) == ["PUMP-101", "PUMP-202"]
            assert sorted(payload["backend_metrics"].keys()) == ["maximo", "mock", "unknown"]
            assert sorted(payload["user_metrics"].keys()) == [
                "operator-1",
                "operator-2",
                "operator-3",
            ]
            assert sorted(payload["org_metrics"].keys()) == ["demo-org"]
            assert payload["asset_metrics"]["PUMP-101"]["early_warning_status"] in {
                "watch",
                "elevated",
                "critical",
            }
            assert payload["asset_metrics"]["PUMP-202"]["early_warning_score"] >= 0
            assert payload["backend_metrics"]["maximo"]["handoff_total"] == 1
            assert payload["backend_metrics"]["maximo"]["handoff_success_rate"] == pytest.approx(
                1.0
            )
            assert payload["backend_metrics"]["mock"]["handoff_total"] == 1
            assert payload["backend_metrics"]["mock"]["handoff_success_rate"] == pytest.approx(1.0)
            assert payload["backend_metrics"]["unknown"]["handoff_total"] == 2
            assert payload["backend_metrics"]["unknown"]["handoff_success_rate"] == pytest.approx(
                0.0
            )
            assert any(
                point["value"] == 1
                for point in payload["backend_metrics"]["mock"]["handoff_volume"]
            )
            assert any(
                point["value"] == 0.0
                for point in payload["backend_metrics"]["unknown"]["handoff_success_rate_series"]
                if point["value"] is not None
            )
            assert payload["user_metrics"]["operator-1"]["feedback_total"] == 1
            assert payload["user_metrics"]["operator-1"]["acceptance_rate"] == pytest.approx(1.0)
            assert payload["org_metrics"]["demo-org"]["feedback_total"] == 3
            assert payload["org_metrics"]["demo-org"]["acceptance_rate"] == pytest.approx(2 / 3)

            volume_points = [
                point
                for point in payload["asset_metrics"]["PUMP-101"]["workorder_volume"]
                if point["value"]
            ]
            assert volume_points == [
                {"date": "2026-03-14", "value": 1},
                {"date": "2026-03-15", "value": 1},
            ]
            acceptance_points = {
                point["date"]: point["value"]
                for point in payload["asset_metrics"]["PUMP-101"]["acceptance_rate"]
                if point["value"] is not None
            }
            assert acceptance_points["2026-03-14"] == pytest.approx(1.0)
            assert acceptance_points["2026-03-15"] == pytest.approx(0.5)

            csv_response = client.get("/api/v1/reports/rca-outcomes/csv?window=30", headers=headers)
            assert csv_response.status_code == 200
            assert "asset_PUMP-101_workorder_volume_2026-03-14,1" in csv_response.text
            assert "asset_PUMP-101_acceptance_rate_2026-03-15,0.5" in csv_response.text
            assert "cmms_success_total,2" in csv_response.text
            assert "cmms_approval_to_handoff_seconds_avg,450.0" in csv_response.text
            assert "cmms_asset_PUMP-202_failure_total,1" in csv_response.text
            assert "cmms_backend_maximo_success_total,1" in csv_response.text
            assert "cmms_backend_mock_approval_to_handoff_seconds_avg,300.0" in csv_response.text
            assert "top_backend_unknown_handoff_count,2" in csv_response.text
            assert "backend_maximo_handoff_total,1" in csv_response.text
            assert "backend_mock_handoff_total,1" in csv_response.text
            assert "backend_unknown_handoff_success_rate,0.0" in csv_response.text
            assert "user_operator-1_feedback_total,1" in csv_response.text
            assert "org_demo-org_feedback_total,3" in csv_response.text
        finally:
            conn.close()
