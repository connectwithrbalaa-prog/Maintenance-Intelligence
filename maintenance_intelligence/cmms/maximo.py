from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from maintenance_intelligence.cmms.adapter import CMMSAdapter, CMMSPayloadError, CMMSUnavailableError, normalize_work_order_result


class MaximoCMMSAdapter(CMMSAdapter):
    backend_name = "maximo"

    def __init__(self, settings, client: Optional[httpx.Client] = None):
        super().__init__(settings)
        self.base_url = getattr(settings, "maximo_base_url", None)
        self.site = getattr(settings, "maximo_site", "BEDFORD")
        self.api_key = getattr(settings, "maximo_api_key", None)
        self.timeout_s = getattr(settings, "maximo_timeout_s", 15)
        self.client = client or httpx.Client(timeout=self.timeout_s)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _endpoint(self) -> str:
        if not self.base_url:
            raise CMMSUnavailableError("Maximo backend is not configured: set MI_MAXIMO_BASE_URL")
        return f"{self.base_url.rstrip('/')}/oslc/os/mxwo"

    def _map_recommendation(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "assetnum": recommendation.get("asset_id"),
            "description": recommendation.get("title"),
            "longdescription": recommendation.get("rationale"),
            "siteid": self.site,
            "priority": recommendation.get("priority", "MEDIUM"),
            "externalrefid": recommendation.get("id"),
        }

    def create_work_order(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._map_recommendation(recommendation)
        try:
            response = self.client.post(self._endpoint(), json=payload, headers=self._headers())
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CMMSUnavailableError("Maximo request failed") from exc

        try:
            body = response.json() if response.content else {}
        except ValueError as exc:
            raise CMMSPayloadError("Maximo returned invalid JSON") from exc
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise CMMSPayloadError("Maximo returned malformed payload")

        return normalize_work_order_result(
            {
                "wo_id": body.get("wonum") or body.get("workorder") or recommendation.get("id"),
                "status": body.get("status", "WAPPR"),
                "backend": self.backend_name,
                "request": payload,
                "response": body,
            },
            recommendation=recommendation,
            backend_name=self.backend_name,
        )