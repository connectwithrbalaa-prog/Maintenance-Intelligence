from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services import rca_agent as rca_mod


def test_estimate_cost_usd_uses_exact_or_prefix_rate(monkeypatch):
    monkeypatch.setenv("MI_RCA_MODEL_RATES", '{"gpt-4.1": 0.5, "default": 0.1}')
    settings = Settings()

    assert rca_mod._estimate_cost_usd(2000, "gpt-4.1", settings) == 1.0
    assert rca_mod._estimate_cost_usd(1000, "gpt-4.1-mini", settings) == 0.5
    assert rca_mod._estimate_cost_usd(1000, "unknown-model", settings) == 0.1


def test_estimate_cost_usd_handles_missing_tokens(monkeypatch):
    monkeypatch.setenv("MI_RCA_MODEL_RATES", '{"gpt-4.1": 0.5}')
    settings = Settings()

    assert rca_mod._estimate_cost_usd(None, "gpt-4.1", settings) == 0.0
    assert rca_mod._estimate_cost_usd(0, "gpt-4.1", settings) == 0.0