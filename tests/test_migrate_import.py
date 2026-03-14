def test_migrate_import():
    import maintenance_intelligence.db.migrate as m
    assert hasattr(m, "run")
