import os
import subprocess
import sys
from urllib.parse import urlparse

import psycopg2
import pytest

RUN_MIGRATION_SMOKE = os.getenv("RUN_MIGRATION_SMOKE", "").lower() in {"1", "true", "yes"}
DATABASE_URL = os.getenv("DATABASE_URL", "")


pytestmark = pytest.mark.skipif(
    not RUN_MIGRATION_SMOKE or not DATABASE_URL,
    reason="Set RUN_MIGRATION_SMOKE=true and DATABASE_URL to run migration smoke tests.",
)


def test_migrate_module_adds_workorder_timestamp_columns() -> None:
    parsed = urlparse(DATABASE_URL)
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    env.update(
        {
            "POSTGRES_DB": (parsed.path or "/maintenance").lstrip("/") or "maintenance",
            "POSTGRES_USER": parsed.username or "postgres",
            "POSTGRES_PASSWORD": parsed.password or "postgres",
            "POSTGRES_HOST": parsed.hostname or "127.0.0.1",
            "POSTGRES_PORT": str(parsed.port or 5432),
            "MI_POSTGRES_DB": (parsed.path or "/maintenance").lstrip("/") or "maintenance",
            "MI_POSTGRES_USER": parsed.username or "postgres",
            "MI_POSTGRES_PASSWORD": parsed.password or "postgres",
            "MI_POSTGRES_HOST": parsed.hostname or "127.0.0.1",
            "MI_POSTGRES_PORT": str(parsed.port or 5432),
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
        dbname=(parsed.path or "/maintenance").lstrip("/") or "maintenance",
        user=parsed.username or "postgres",
        password=parsed.password or "postgres",
        host=parsed.hostname or "127.0.0.1",
        port=str(parsed.port or 5432),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("""
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
                """)
            columns = [row[0] for row in cur.fetchall()]
            assert columns == [
                "handoff_completed_at",
                "workorder_completed_at",
                "workorder_created_at",
            ]

            cur.execute("SELECT to_regclass('public.alembic_version')")
            alembic_table = cur.fetchone()[0]
            if alembic_table == "alembic_version":
                cur.execute("SELECT version_num FROM alembic_version")
                assert cur.fetchone()[0] == "005_rca_feedback"
            else:
                cur.execute(
                    "SELECT filename FROM mi_schema_migrations WHERE filename = %s",
                    ("011_rename_event_time_to_occurred_at.sql",),
                )
                assert cur.fetchone()[0] == "011_rename_event_time_to_occurred_at.sql"
    finally:
        conn.close()
