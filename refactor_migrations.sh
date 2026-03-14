set -euo pipefail
BRANCH="feature/migrations-and-health"

git fetch origin
git checkout -b "$BRANCH" || git checkout "$BRANCH"

# Folders
mkdir -p maintenance_intelligence/db/migrations maintenance_intelligence/api

# Minimal SQL-first migrations with idempotent guards
cat > maintenance_intelligence/db/migrations/001_init.sql << 'SQL'
-- events table
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  event_time TIMESTAMPTZ,
  org_id TEXT,
  asset_id TEXT,
  kind TEXT,
  severity TEXT,
  summary TEXT,
  details JSONB,
  lineage JSONB
);

-- workorders table
CREATE TABLE IF NOT EXISTS workorders (
  wo_id TEXT PRIMARY KEY,
  asset_id TEXT,
  status TEXT,
  title TEXT,
  description TEXT,
  priority TEXT,
  metadata JSONB
);

-- optional doc_chunks stub for RAG
CREATE TABLE IF NOT EXISTS doc_chunks (
  chunk_id TEXT PRIMARY KEY,
  asset_id TEXT,
  title TEXT,
  content TEXT,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
SQL

# Simple migration runner (applies SQL files once; stores applied filenames)
cat > maintenance_intelligence/db/migrate.py << 'PY'
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
PY

# Stronger health checks: Kafka + PG
cat > maintenance_intelligence/api/health.py << 'PY'
from fastapi import APIRouter, Query
from maintenance_intelligence.runner.config import Settings
import socket, psycopg2
from kafka import KafkaAdminClient

router = APIRouter()

@router.get("/healthz")
def healthz(deep: bool = Query(False, description="Enable deep checks (Kafka/PG)")):
    info = {"status": "ok", "host": socket.gethostname()}
    if not deep:
        return info

    settings = Settings()
    # PG check
    try:
        conn = psycopg2.connect(settings.pg_dsn)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            info["pg"] = "ok"
        finally:
            conn.close()
    except Exception as e:
        info["pg"] = f"error: {e}"
        info["status"] = "degraded"

    # Kafka check
    try:
        admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap, client_id="mi-health")
        topics = admin.list_topics()
        info["kafka"] = "ok" if topics is not None else "unknown"
    except Exception as e:
        info["kafka"] = f"error: {e}"
        info["status"] = "degraded"

    return info
PY

# Ensure health router is mounted
if ! grep -q "health_router" maintenance_intelligence/api/main.py; then
  sed -i '1i from maintenance_intelligence.api.health import router as health_router' maintenance_intelligence/api/main.py
  sed -i 's/app = FastAPI.*/&\napp.include_router(health_router)/' maintenance_intelligence/api/main.py
fi

# README snippet
cat >> README.md << 'PY'

## Database Migrations & Health Checks

- Run migrations:
  - python -m maintenance_intelligence.db.migrate
- Health endpoint:
  - GET /healthz (basic)
  - GET /healthz?deep=true (PG + Kafka checks)
PY

# Basic test: migration runner importable
cat > tests/test_migrate_import.py << 'PY'
def test_migrate_import():
    import maintenance_intelligence.db.migrate as m
    assert hasattr(m, "run")
PY

# Commit & push
git add .
git commit -m "feat: SQL-first migrations + deep health checks (/healthz?deep=true) + migration runner"
git push -u origin "$BRANCH"