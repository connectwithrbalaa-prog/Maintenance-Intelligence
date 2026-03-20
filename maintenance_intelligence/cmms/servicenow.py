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


class ServiceNowCMMSAdapter(CMMSAdapter):
    backend_name = "servicenow"
    backend_label = "ServiceNow"
    backend_description = "ServiceNow work order REST connector scaffold"
    lifecycle_status_map = {
        "NEW": "handoff-complete",
        "OPEN": "active",
        "WORK_IN_PROGRESS": "active",
        "CLOSED_COMPLETE": "completed",
        "CLOSED_SKIPPED": "completed",
    }
    config_fields = [
        {
            "setting_name": "servicenow_base_url",
            "env_var": "MI_SERVICENOW_BASE_URL",
            "required": True,
            "description": "Base URL for the ServiceNow instance.",
        },
        {
            "setting_name": "servicenow_table",
            "env_var": "MI_SERVICENOW_TABLE",
            "required": False,
            "default": "wm_order",
            "description": "ServiceNow table name used for work order creates.",
        },
        {
            "setting_name": "servicenow_username",
            "env_var": "MI_SERVICENOW_USERNAME",
            "required": False,
            "secret": True,
            "description": "Optional ServiceNow basic-auth username.",
        },
        {
            "setting_name": "servicenow_password",
            "env_var": "MI_SERVICENOW_PASSWORD",
            "required": False,
            "secret": True,
            "description": "Optional ServiceNow basic-auth password.",
        },
        {
            "setting_name": "servicenow_timeout_s",
            "env_var": "MI_SERVICENOW_TIMEOUT_S",
            "required": False,
            "default": 15,
            "description": "HTTP timeout in seconds for ServiceNow requests.",
        },
    ]

    def __init__(self, settings, client: Optional[httpx.Client] = None):
        super().__init__(settings)
        self.base_url = getattr(settings, "servicenow_base_url", None)
        self.table = getattr(settings, "servicenow_table", "wm_order")
        self.username = getattr(settings, "servicenow_username", None)
        self.password = getattr(settings, "servicenow_password", None)
        self.timeout_s = getattr(settings, "servicenow_timeout_s", 15)
        auth = (
            httpx.BasicAuth(self.username, self.password)
            if self.username and self.password
            else None
        )
        self.client = client or httpx.Client(timeout=self.timeout_s, auth=auth)

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _endpoint(self) -> str:
        if not self.base_url:
            raise CMMSConfigurationError(
                "ServiceNow backend is not configured: set MI_SERVICENOW_BASE_URL"
            )
        return f"{self.base_url.rstrip('/')}/api/now/table/{self.table}"

    def _map_recommendation(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "short_description": recommendation.get("title"),
            "description": recommendation.get("rationale"),
            "cmdb_ci": recommendation.get("asset_id"),
            "priority": recommendation.get("priority", "MEDIUM"),
            "u_external_reference_id": recommendation.get("id"),
        }

    def _unwrap_body(self, body: Any) -> Dict[str, Any]:
        if body is None:
            return {}
        if isinstance(body, dict) and isinstance(body.get("result"), dict):
            return body.get("result") or {}
        if isinstance(body, dict):
            return body
        return {}

    def create_work_order(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._map_recommendation(recommendation)
        response = post_json_request(
            self.client,
            endpoint=self._endpoint(),
            payload=payload,
            headers=self._headers(),
            unavailable_detail="ServiceNow request failed",
        )
        body = parse_json_response_body(
            response,
            invalid_json_detail="ServiceNow returned invalid JSON",
            malformed_payload_detail="ServiceNow returned malformed payload",
            unwrap=self._unwrap_body,
        )

        return normalize_work_order_result(
            {
                **translate_connector_response(
                    body,
                    backend_name=self.backend_name,
                    recommendation=recommendation,
                    wo_id_fields=("number", "sys_id"),
                    status_fields=("state_display", "state", "status"),
                    message_fields=("message", "status_message"),
                    workorder_created_fields=(
                        "sys_created_on",
                        "opened_at",
                        "workorder_created_at",
                    ),
                    handoff_completed_fields=("sys_created_on", "opened_at"),
                    workorder_completed_fields=("closed_at", "work_end", "workorder_completed_at"),
                    default_status="NEW",
                ),
                "request": payload,
            },
            recommendation=recommendation,
            backend_name=self.backend_name,
            lifecycle_status_map=self.lifecycle_status_map,
        )
