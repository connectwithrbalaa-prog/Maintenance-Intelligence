import os
import subprocess
import sys

import psycopg2
import pytest


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
def test_migrate_module_applies_schema_to_ephemeral_postgres() -> None:
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

        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=host,
            port=port,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        to_regclass('public.events'),
                        to_regclass('public.pm_proposals'),
                        to_regclass('public.workorders'),
                        to_regclass('public.rca_feedback'),
                        to_regclass('public.repair_plan'),
                        to_regclass('public.repair_part'),
                        to_regclass('public.alembic_version'),
                        to_regclass('public.mi_schema_migrations')
                    """
                )
                events_table, pm_proposals_table, workorders_table, rca_feedback_table, repair_plan_table, repair_part_table, alembic_table, fallback_table = cur.fetchone()

                assert events_table == "events"
                assert pm_proposals_table == "pm_proposals"
                assert workorders_table == "workorders"
                assert rca_feedback_table == "rca_feedback"
                assert repair_plan_table == "repair_plan"
                assert repair_part_table == "repair_part"
                assert alembic_table == "alembic_version" or fallback_table == "mi_schema_migrations"

                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'workorders'
                      AND column_name IN (
                          'workorder_created_at',
                          'handoff_completed_at',
                          'workorder_completed_at'
                      )
                    ORDER BY column_name
                    """
                )
                assert [row[0] for row in cur.fetchall()] == [
                    'handoff_completed_at',
                    'workorder_completed_at',
                    'workorder_created_at',
                ]

                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'events'
                      AND column_name IN ('event_time', 'occurred_at')
                    ORDER BY column_name
                    """
                )
                assert [row[0] for row in cur.fetchall()] == ['occurred_at']

                if alembic_table == "alembic_version":
                    cur.execute("SELECT version_num FROM alembic_version")
                    assert cur.fetchone()[0] == "006_repair_plan_and_parts"
                else:
                    cur.execute(
                        "SELECT filename FROM mi_schema_migrations WHERE filename = %s",
                        ("012_repair_plan_and_parts.sql",),
                    )
                    assert cur.fetchone()[0] == "012_repair_plan_and_parts.sql"
        finally:
            conn.close()