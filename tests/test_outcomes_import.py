from maintenance_intelligence.api import outcomes


def test_outcomes_imports():
    assert hasattr(outcomes, "rca_outcomes")