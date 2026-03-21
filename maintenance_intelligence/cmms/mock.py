from __future__ import annotations

import datetime as dt
from typing import Any, Dict

from maintenance_intelligence.cmms.adapter import CMMSAdapter, normalize_work_order_result


class MockCMMSAdapter(CMMSAdapter):
    backend_name = "mock"

    def create_work_order(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        rec_id = recommendation.get("id", "")
        return normalize_work_order_result(
            {
                "wo_id": f"WO-{rec_id[:8]}",
                "status": "DRAFT",
                "backend": self.backend_name,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "request": {
                    "asset_id": recommendation.get("asset_id"),
                    "title": recommendation.get("title"),
                },
            },
            recommendation=recommendation,
            backend_name=self.backend_name,
        )
