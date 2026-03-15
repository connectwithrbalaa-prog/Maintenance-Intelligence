from pathlib import Path


def test_demo_pm_script_exists() -> None:
    script = Path("scripts/demo_pm_approval.sh")
    contents = script.read_text(encoding="utf-8")

    assert script.exists()
    assert contents.startswith("#!/usr/bin/env bash")
    assert "--use-existing-api" in contents
    assert "pretty_print_json" in contents