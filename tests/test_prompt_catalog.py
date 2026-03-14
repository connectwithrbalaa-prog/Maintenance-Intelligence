from maintenance_intelligence.prompts.catalog import choose_prompt_variant


def test_choose_prompt_variant_canary_split():
    prompts = {
        "rca-default-v1": {"prompt_id": "rca-default-v1"},
        "rca-canary-v1": {"prompt_id": "rca-canary-v1"},
    }
    route_config = {
        "route_name": "rca",
        "default_prompt_id": "rca-default-v1",
        "canary_prompt_id": "rca-canary-v1",
        "canary_ratio": 0.1,
        "auto_rollback_enabled": False,
    }

    canary = choose_prompt_variant(prompts, route_config, "evt-1", subject_bucket=0.05)
    default = choose_prompt_variant(prompts, route_config, "evt-2", subject_bucket=0.55)

    assert canary["prompt_id"] == "rca-canary-v1"
    assert canary["variant"] == "canary"
    assert default["prompt_id"] == "rca-default-v1"
    assert default["variant"] == "default"


def test_choose_prompt_variant_auto_rolls_back_underperforming_canary():
    prompts = {
        "rca-default-v1": {"prompt_id": "rca-default-v1"},
        "rca-canary-v1": {"prompt_id": "rca-canary-v1"},
    }
    route_config = {
        "route_name": "rca",
        "default_prompt_id": "rca-default-v1",
        "canary_prompt_id": "rca-canary-v1",
        "canary_ratio": 0.5,
        "auto_rollback_enabled": True,
        "rollback_min_runs": 5,
        "rollback_acceptance_delta": 0.05,
    }
    stats = {
        "rca-default-v1": {"total": 10, "accept": 8},
        "rca-canary-v1": {"total": 10, "accept": 2},
    }

    selected = choose_prompt_variant(
        prompts, route_config, "evt-3", feedback_stats=stats, subject_bucket=0.01
    )

    assert selected["prompt_id"] == "rca-default-v1"
    assert selected["variant"] == "default"
    assert selected["auto_rollback_triggered"] is True
