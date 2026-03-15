from pathlib import Path


def test_migrate_import():
    import maintenance_intelligence.db.migrate as m
    assert hasattr(m, "run")


def test_dev_compose_bootstraps_migrations_before_api_start():
    compose_text = Path("docker-compose.dev.yml").read_text()

    assert "migrator:" in compose_text
    assert "python -m maintenance_intelligence.db.migrate" in compose_text
    assert "pg_isready -U postgres -d maintenance" in compose_text
    assert "migrator:\n        condition: service_completed_successfully" in compose_text
