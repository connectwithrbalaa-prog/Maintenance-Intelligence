import builtins
import sys
from pathlib import Path
from types import SimpleNamespace


class FakeAlembicConfig:
    def __init__(self):
        self.options = {}

    def set_main_option(self, key, value):
        self.options[key] = value


class FakeCursor:
    def __init__(self, already_applied=None):
        self.already_applied = set(already_applied or [])
        self.executed = []
        self._fetchone = None

    def execute(self, query, params=None):
        self.executed.append((query, params))
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT 1 FROM mi_schema_migrations"):
            self._fetchone = (1,) if params and params[0] in self.already_applied else None
            return
        if normalized.startswith("INSERT INTO mi_schema_migrations"):
            self.already_applied.add(params[0])
        self._fetchone = None

    def fetchone(self):
        return self._fetchone

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, already_applied=None):
        self.cursor_obj = FakeCursor(already_applied=already_applied)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_migrate_import():
    import maintenance_intelligence.db.migrate as m
    assert hasattr(m, "run")


def test_dev_compose_bootstraps_migrations_before_api_start():
    compose_text = Path("docker-compose.dev.yml").read_text()

    assert "migrator:" in compose_text
    assert "python -m maintenance_intelligence.db.migrate" in compose_text
    assert "pg_isready -U postgres -d maintenance" in compose_text
    assert "migrator:\n        condition: service_completed_successfully" in compose_text


def test_run_uses_alembic_when_available(monkeypatch):
    import maintenance_intelligence.db.migrate as migrate_mod

    upgrade_calls = []
    info_events = []

    fake_alembic_module = SimpleNamespace(
        command=SimpleNamespace(upgrade=lambda cfg, rev: upgrade_calls.append((cfg, rev)))
    )
    fake_alembic_config_module = SimpleNamespace(Config=FakeAlembicConfig)

    monkeypatch.setattr(
        migrate_mod,
        "Settings",
        lambda: SimpleNamespace(
            sqlalchemy_url="postgresql://tester:secret@db:5432/maintenance",
            pg_dsn="unused",
        ),
    )
    monkeypatch.setattr(migrate_mod.logger, "info", lambda payload: info_events.append(payload))
    monkeypatch.setitem(sys.modules, "alembic", fake_alembic_module)
    monkeypatch.setitem(sys.modules, "alembic.config", fake_alembic_config_module)

    migrate_mod.run()

    assert len(upgrade_calls) == 1
    alembic_cfg, revision = upgrade_calls[0]
    assert revision == "head"
    assert alembic_cfg.options["script_location"] == "maintenance_intelligence/db/alembic"
    assert alembic_cfg.options["sqlalchemy.url"] == "postgresql://tester:secret@db:5432/maintenance"
    assert info_events == [
        {"event": "migration.start", "using": "alembic"},
        {"event": "migration.done"},
    ]


def test_run_falls_back_to_sql_migrations_when_alembic_missing(monkeypatch, tmp_path):
    import maintenance_intelligence.db.migrate as migrate_mod

    first_file = tmp_path / "migrations" / "001_init.sql"
    second_file = tmp_path / "migrations" / "002_next.sql"
    first_file.parent.mkdir(parents=True)
    first_file.write_text("SELECT 1;", encoding="utf-8")
    second_file.write_text("SELECT 2;", encoding="utf-8")

    fake_conn = FakeConnection(already_applied={"001_init.sql"})
    warning_events = []
    info_events = []
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"alembic", "alembic.config"}:
            raise ImportError("alembic unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(migrate_mod, "__file__", str(tmp_path / "migrate.py"))
    monkeypatch.setattr(
        migrate_mod,
        "Settings",
        lambda: SimpleNamespace(sqlalchemy_url="unused", pg_dsn="dbname=maintenance"),
    )
    monkeypatch.setattr(migrate_mod.logger, "warning", lambda payload: warning_events.append(payload))
    monkeypatch.setattr(migrate_mod.logger, "info", lambda payload: info_events.append(payload))
    monkeypatch.setitem(sys.modules, "glob", SimpleNamespace(glob=lambda pattern: [str(first_file), str(second_file)]))
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=lambda dsn: fake_conn))

    migrate_mod.run()

    executed_queries = [query for query, _params in fake_conn.cursor_obj.executed]
    assert any("CREATE TABLE IF NOT EXISTS mi_schema_migrations" in query for query in executed_queries)
    assert any(query == "SELECT 2;" for query in executed_queries)
    assert not any(query == "SELECT 1;" for query in executed_queries)
    assert warning_events == [
        {"event": "migration.fallback", "reason": "alembic not available, using legacy SQL migrations"}
    ]
    assert {event["event"] for event in info_events} == {"migration.skip", "migration.apply", "migration.done"}
    assert fake_conn.closed is True
