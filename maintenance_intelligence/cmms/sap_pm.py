from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from maintenance_intelligence.cmms.adapter import (
    CMMSAdapter,
    CMMSConfigurationError,
    CMMSPayloadError,
    normalize_work_order_result,
    parse_json_response_body,
    post_json_request,
)
from maintenance_intelligence.cmms.translators import translate_connector_response


class SAPPMCMMSAdapter(CMMSAdapter):
    backend_name = "sap_pm"
    backend_label = "SAP PM"
    backend_description = "SAP Plant Maintenance OData connector scaffold"
    lifecycle_status_map = {
        "REL": "handoff-complete",
        "PCNF": "active",
        "CNF": "active",
        "TECO": "completed",
        "CLSD": "completed",
    }
    config_fields = [
        {
            "setting_name": "sap_pm_base_url",
            "env_var": "MI_SAP_PM_BASE_URL",
            "required": True,
            "description": "Base URL for the SAP PM environment.",
        },
        {
            "setting_name": "sap_pm_plant",
            "env_var": "MI_SAP_PM_PLANT",
            "required": False,
            "default": "1000",
            "description": "Default plant used when creating work orders.",
        },
        {
            "setting_name": "sap_pm_order_type",
            "env_var": "MI_SAP_PM_ORDER_TYPE",
            "required": False,
            "default": "PM01",
            "description": "Default SAP PM order type.",
        },
        {
            "setting_name": "sap_pm_username",
            "env_var": "MI_SAP_PM_USERNAME",
            "required": False,
            "secret": True,
            "description": "Optional SAP PM basic-auth username.",
        },
        {
            "setting_name": "sap_pm_password",
            "env_var": "MI_SAP_PM_PASSWORD",
            "required": False,
            "secret": True,
            "description": "Optional SAP PM basic-auth password.",
        },
        {
            "setting_name": "sap_pm_timeout_s",
            "env_var": "MI_SAP_PM_TIMEOUT_S",
            "required": False,
            "default": 15,
            "description": "HTTP timeout in seconds for SAP PM requests.",
        },
    ]

    def __init__(self, settings, client: Optional[httpx.Client] = None):
        super().__init__(settings)
        self.base_url = getattr(settings, "sap_pm_base_url", None)
        self.plant = getattr(settings, "sap_pm_plant", "1000")
        self.order_type = getattr(settings, "sap_pm_order_type", "PM01")
        self.username = getattr(settings, "sap_pm_username", None)
        self.password = getattr(settings, "sap_pm_password", None)
        self.timeout_s = getattr(settings, "sap_pm_timeout_s", 15)
        auth = httpx.BasicAuth(self.username, self.password) if self.username and self.password else None
        self.client = client or httpx.Client(timeout=self.timeout_s, auth=auth)

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _endpoint(self) -> str:
        if not self.base_url:
            raise CMMSConfigurationError("SAP PM backend is not configured: set MI_SAP_PM_BASE_URL")
        return (
            f"{self.base_url.rstrip('/')}/sap/opu/odata/sap/"
            "ZMI_WORKORDER_SRV/WorkOrders"
        )

    def _map_recommendation(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "Equipment": recommendation.get("asset_id"),
            "ShortText": recommendation.get("title"),
            "Description": recommendation.get("rationale"),
            "Plant": self.plant,
            "OrderType": recommendation.get("order_type") or self.order_type,
            "Priority": recommendation.get("priority", "MEDIUM"),
            "ExternalReferenceId": recommendation.get("id"),
        }

    def _unwrap_body(self, body: Any) -> Dict[str, Any]:
        if body is None:
            return {}
        if isinstance(body, dict) and isinstance(body.get("d"), dict):
            return body.get("d") or {}
        if isinstance(body, dict):
            return body
        raise CMMSPayloadError("SAP PM returned malformed payload")

    def create_work_order(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._map_recommendation(recommendation)
        response = post_json_request(
            self.client,
            endpoint=self._endpoint(),
            payload=payload,
            headers=self._headers(),
            unavailable_detail="SAP PM request failed",
        )
        body = parse_json_response_body(
            response,
            invalid_json_detail="SAP PM returned invalid JSON",
            malformed_payload_detail="SAP PM returned malformed payload",
            unwrap=self._unwrap_body,
        )

        return normalize_work_order_result(
            {
                **translate_connector_response(
                    body,
                    backend_name=self.backend_name,
                    recommendation=recommendation,
                    wo_id_fields=("OrderNumber", "MaintenanceOrder"),
                    status_fields=("OrderStatus", "Status"),
                    message_fields=("Message",),
                    workorder_created_fields=("CreatedAt",),
                    handoff_completed_fields=("SystemStatusDate", "CreatedAt"),
                    workorder_completed_fields=("CompletedAt", "TechnicalCompletionDate"),
                    default_status="REL",
                ),
                "request": payload,
            },
            recommendation=recommendation,
            backend_name=self.backend_name,
            lifecycle_status_map=self.lifecycle_status_map,
        )