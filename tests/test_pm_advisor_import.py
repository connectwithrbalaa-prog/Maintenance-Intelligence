import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_pm_advisor_modules_import():
    pm_advisor = importlib.import_module("maintenance_intelligence.api.pm_advisor")
    playbook_agent = importlib.import_module("maintenance_intelligence.services.playbook_agent")
    pm_advisor_agent = importlib.import_module("maintenance_intelligence.services.pm_advisor_agent")
    assert hasattr(pm_advisor, "router")
    assert hasattr(pm_advisor_agent, "analyze_pm_strategy")
    assert hasattr(playbook_agent, "search_playbooks")