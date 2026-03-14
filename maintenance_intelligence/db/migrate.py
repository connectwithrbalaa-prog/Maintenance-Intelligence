import os, glob, psycopg2
from loguru import logger
from maintenance_intelligence.runner.config import Settings

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

def run():
    settings = Settings()
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
