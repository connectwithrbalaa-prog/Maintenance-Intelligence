def test_reports_import():
    from maintenance_intelligence.api import reports
    assert hasattr(reports, "bad_actors")
