import os
import subprocess
import sys

import psycopg2
import pytest


RUN_MIGRATION_SMOKE = os.getenv("RUN_MIGRATION_SMOKE", "").lower() in {"1", "true", "yes"}
DATABASE_URL = os.getenv("DATABASE_URL", "")


pytestmark = pytest.mark.skipif(
    not RUN_MIGRATION_SMOKE or not DATABASE_URL,
    reason="Set RUN_MIGRATION_SMOKE=true and DATABASE_URL to run migration smoke tests.",
)


def test_migrate_module_adds_workorder_timestamp_columns() -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL

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

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
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
            columns = [row[0] for row in cur.fetchall()]
            assert columns == [
                'handoff_completed_at',
                'workorder_completed_at',
                'workorder_created_at',
            ]

            cur.execute("SELECT to_regclass('public.alembic_version')")
            alembic_table = cur.fetchone()[0]
            if alembic_table == 'alembic_version':
                cur.execute("SELECT version_num FROM alembic_version")
                assert cur.fetchone()[0] == '003_add_workorder_timestamps'
            else:
                cur.execute(
                    "SELECT filename FROM mi_schema_migrations WHERE filename = %s",
                    ('010_add_workorder_timestamps.sql',),
                )
                assert cur.fetchone()[0] == '010_add_workorder_timestamps.sql'
    finally:
        conn.close()
