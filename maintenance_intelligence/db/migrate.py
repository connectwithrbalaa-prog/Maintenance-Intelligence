import os
import sys
from loguru import logger
from maintenance_intelligence.runner.config import Settings

def run():
    """Run database migrations using Alembic."""
    try:
        from alembic.config import Config
        from alembic import command

        # Get database URL
        settings = Settings()
        db_url = settings.sqlalchemy_url

        # Configure Alembic
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", "maintenance_intelligence/db/alembic")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        os.environ["DATABASE_URL"] = db_url

        # Run migrations
        logger.info({"event": "migration.start", "using": "alembic"})
        command.upgrade(alembic_cfg, "head")
        logger.info({"event": "migration.done"})

    except ImportError:
        logger.warning({"event": "migration.fallback", "reason": "alembic not available, using legacy SQL migrations"})

        # Fallback to legacy SQL migrations
        import glob, psycopg2

        DDL_TRACK_TABLE = "mi_schema_migrations"

        def ensure_track_table(cur):
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {DDL_TRACK_TABLE} (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT now()
                )
            """)

        def already_applied(cur, fname: str) -> bool:
            cur.execute(f"SELECT 1 FROM {DDL_TRACK_TABLE} WHERE filename = %s", (fname,))
            return cur.fetchone() is not None

        def apply_sql(cur, sql_text: str):
            cur.execute(sql_text)

        conn = psycopg2.connect(settings.pg_dsn)
        try:
            with conn:
                with conn.cursor() as cur:
                    ensure_track_table(cur)
                    files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "migrations", "*.sql")))
                    for f in files:
                        name = os.path.basename(f)
                        if already_applied(cur, name):
                            logger.info({"event":"migration.skip","file":name})
                            continue
                        with open(f, "r") as fh:
                            sql_text = fh.read()
                        logger.info({"event":"migration.apply","file":name})
                        apply_sql(cur, sql_text)
                        cur.execute(f"INSERT INTO {DDL_TRACK_TABLE} (filename) VALUES (%s)", (name,))
            logger.info({"event":"migration.done"})
        finally:
            conn.close()

if __name__ == "__main__":
    run()
