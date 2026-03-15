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
                            "EVT-1", "2026-03-14T08:00:00Z", "demo-org", "PUMP-101", "alarm", "high", "High vibration", json.dumps({"rms": 8.5}), json.dumps({"source": "smoke"}),
                            "EVT-2", "2026-03-15T08:00:00Z", "demo-org", "PUMP-101", "alarm", "high", "High vibration persisted", json.dumps({"rms": 8.9}), json.dumps({"source": "smoke"}),
                            "EVT-3", "2026-03-15T10:30:00Z", "demo-org", "PUMP-202", "alarm", "medium", "Temperature alert", json.dumps({"temp": 91}), json.dumps({"source": "smoke"}),
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
                            "WO-1", "PUMP-101", "COMP", "Inspect pump seal", "Seal wear suspected", "HIGH", json.dumps({"evidence_event_id": "EVT-1"}),
                            "2026-03-14T10:00:00Z", "2026-03-14T10:05:00Z", "2026-03-14T13:00:00Z",
                            "WO-2", "PUMP-101", "DONE", "Replace coupling", "Coupling wear confirmed", "MEDIUM", json.dumps({"evidence_event_id": "EVT-2"}),
                            "2026-03-15T10:00:00Z", "2026-03-15T10:03:00Z", "2026-03-15T14:00:00Z",
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
                            "FB-1", "RUN-1", "REC-1", "demo-org", "PUMP-101", "accept", json.dumps({}), "good recommendation", "operator-1", "2026-03-14T12:00:00Z",
                            "FB-2", "RUN-2", "REC-2", "demo-org", "PUMP-101", "reject", json.dumps({}), "not needed", "operator-2", "2026-03-15T12:00:00Z",
                            "FB-3", "RUN-3", "REC-3", "demo-org", "PUMP-101", "accept", json.dumps({}), "completed", "operator-3", "2026-03-15T13:00:00Z",
                        ),
                    )

            client = TestClient(app)
            response = client.get("/api/v1/reports/rca-outcomes?window=30")
            assert response.status_code == 200
            payload = response.json()

            assert payload["status"] == "ok"
            assert payload["feedback_counts"] == {"accept": 2, "reject": 1, "edited": 0}
            assert payload["feedback_total"] == 3
            assert payload["acceptance_rate"] == pytest.approx(2 / 3)
            assert payload["ttr_seconds_avg"] == pytest.approx(7200.0)
            assert payload["mtbf_seconds_avg"] == pytest.approx(86400.0)
            assert payload["mttr_seconds_avg"] == pytest.approx(12600.0)
            assert payload["top_assets_by_wo_volume"] == [{"asset_id": "PUMP-101", "count": 2}]
            assert payload["placeholders"] == {}
            assert sorted(payload["asset_metrics"].keys()) == ["PUMP-101"]

            volume_points = [point for point in payload["asset_metrics"]["PUMP-101"]["workorder_volume"] if point["value"]]
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

            csv_response = client.get("/api/v1/reports/rca-outcomes/csv?window=30")
            assert csv_response.status_code == 200
            assert "asset_PUMP-101_workorder_volume_2026-03-14,1" in csv_response.text
            assert "asset_PUMP-101_acceptance_rate_2026-03-15,0.5" in csv_response.text
        finally:
            conn.close()
