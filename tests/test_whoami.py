import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from maintenance_intelligence.api.main import app


def test_whoami_header_fallback():
    client = TestClient(app)

    response = client.get(
        "/api/v1/whoami",
        headers={
            "X-Org-Id": "org-demo",
            "X-Role": "operator",
            "X-Subject": "portal-user",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "org_id": "org-demo",
        "role": "operator",
        "subject": "portal-user",
    }