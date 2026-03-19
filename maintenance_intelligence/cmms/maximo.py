from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from maintenance_intelligence.cmms.adapter import (
    CMMSAdapter,
    CMMSConfigurationError,
    normalize_work_order_result,
    parse_json_response_body,
    post_json_request,
)
from maintenance_intelligence.cmms.translators import translate_connector_response


class MaximoCMMSAdapter(CMMSAdapter):
    backend_name = "maximo"
    backend_label = "IBM Maximo"
    backend_description = "Maximo OSLC work order connector scaffold"
    lifecycle_status_map = {
        "WAPPR": "handoff-complete",
        "APPR": "handoff-complete",
        "INPRG": "active",
        "WMATL": "active",
        "COMP": "completed",
        "CLOSE": "completed",
    }
    config_fields = [
        {
            "setting_name": "maximo_base_url",
            "env_var": "MI_MAXIMO_BASE_URL",
            "required": True,
            "description": "Base URL for the Maximo environment.",
        },
        {
            "setting_name": "maximo_site",
            "env_var": "MI_MAXIMO_SITE",
            "required": False,
            "default": "BEDFORD",
            "description": "Default Maximo site id for created work orders.",
        },
        {
            "setting_name": "maximo_api_key",
            "env_var": "MI_MAXIMO_API_KEY",
            "required": False,
            "secret": True,
            "description": "Optional API key sent in the x-api-key header.",
        },
        {
            "setting_name": "maximo_timeout_s",
            "env_var": "MI_MAXIMO_TIMEOUT_S",
            "required": False,
            "default": 15,
            "description": "HTTP timeout in seconds for Maximo requests.",
        },
    ]

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
            raise CMMSConfigurationError("Maximo backend is not configured: set MI_MAXIMO_BASE_URL")
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
        response = post_json_request(
            self.client,
            endpoint=self._endpoint(),
            payload=payload,
            headers=self._headers(),
            unavailable_detail="Maximo request failed",
        )
        body = parse_json_response_body(
            response,
            invalid_json_detail="Maximo returned invalid JSON",
            malformed_payload_detail="Maximo returned malformed payload",
        )

        return normalize_work_order_result(
            {
                **translate_connector_response(
                    body,
                    backend_name=self.backend_name,
                    recommendation=recommendation,
                    wo_id_fields=("wonum", "workorder"),
                    status_fields=("status",),
                    workorder_created_fields=("workorder_created_at", "created_at"),
                    handoff_completed_fields=("handoff_completed_at", "statusdate", "changedate"),
                    workorder_completed_fields=("workorder_completed_at", "actfinish", "completed_at", "closed_at", "finishdate"),
                    default_status="WAPPR",
                ),
                "request": payload,
            },
            recommendation=recommendation,
            backend_name=self.backend_name,
            lifecycle_status_map=self.lifecycle_status_map,
        )