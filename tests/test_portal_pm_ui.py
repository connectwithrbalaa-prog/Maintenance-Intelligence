import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_intelligence.api.main import app


def test_portal_pm_ui_served():
    client = TestClient(app)

    response = client.get("/portal/pm-approvals")

    assert response.status_code == 200
    assert "PM approval queue for planner review" in response.text
    assert "/api/v1/agents/pm/proposals" in response.text
    assert "/api/v1/whoami" in response.text
    assert "Portal API returned invalid JSON" in response.text
    assert "No draft PM proposals available." in response.text