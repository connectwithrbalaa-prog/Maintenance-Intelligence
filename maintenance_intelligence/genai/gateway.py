import time
from typing import Any, Dict, Optional
from loguru import logger

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from maintenance_intelligence.ai.prompts.rca_templates import (
    SYSTEM_PROMPT,
    build_rca_prompt,
)
from maintenance_intelligence.ai.rag.structured_retriever import RCAContext


class GenAIGateway:
    def __init__(self, api_key: str, model: str, timeout_s: int = 25):
        self.model = model
        self.timeout_s = timeout_s
        if OpenAI is None:
            raise RuntimeError("openai package not installed")
        self.client = OpenAI(api_key=api_key)

    def call_rca(
        self,
        event: Dict[str, Any],
        context: Dict[str, Any],
        iso_context: Optional[RCAContext] = None,
    ) -> Dict[str, Any]:
        t0 = time.time()
        prompt = self._build_prompt(event, context, iso_context=iso_context)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                timeout=self.timeout_s,
            )
            text = resp.choices[0].message.content.strip() if resp.choices else ""
            usage = getattr(resp, "usage", None)
            tokens = usage.total_tokens if usage else None
        except Exception as e:
            logger.error({"event": "genai.error", "err": str(e)})
            text, tokens = f"[GENAI_ERROR] {e}", None

        latency = int((time.time() - t0) * 1000)
        structured = self._parse_structured(text)
        return {
            "text": text,
            "structured": structured,
            "model_version": self.model,
            "tokens": tokens,
            "latency_ms": latency,
        }

    def _build_prompt(
        self,
        event: Dict[str, Any],
        context: Dict[str, Any],
        iso_context: Optional[RCAContext] = None,
    ) -> str:
        event_summary = event.get("summary") or f"{event.get('kind', 'event')} on {event.get('asset_id', 'unknown')}"

        if iso_context:
            return build_rca_prompt(
                event_summary,
                context=iso_context,
                asset_id=event.get("asset_id"),
                event_kind=event.get("kind"),
                severity=event.get("severity"),
            )

        lines = [
            "Respond with STRICT JSON only. Do NOT include markdown, backticks, or commentary.",
            "Use ISO 14224 failure classification codes where applicable.",
            self._JSON_SCHEMA_INSTRUCTION,
            f"Event: {event_summary}",
            f"Asset: {event.get('asset_id', 'unknown')}",
            f"Kind: {event.get('kind', 'unknown')}",
            f"Severity: {event.get('severity', 'unknown')}",
        ]
        if context.get("last_wo_titles"):
            lines.append(f"Recent work orders: {context['last_wo_titles']}")
        if context.get("recent_signals"):
            lines.append(f"Recent signals: {context['recent_signals'][:5]}")
        if context.get("doc_chunks"):
            lines.append(f"Reference docs: {[c.get('title') for c in context['doc_chunks'][:3]]}")
        return "\n".join(lines)


    _JSON_SCHEMA_INSTRUCTION = (
        'Output schema (strict JSON):\n'
        '{\n'
        '  "title": "string", "summary": "string",\n'
        '  "failure_mode_code": "ISO 14224 code e.g. VIB, ELP, FTS",\n'
        '  "failure_mechanism_code": "ISO 14224 code e.g. WEA, COR, FAT",\n'
        '  "failure_cause_code": "ISO 14224 code e.g. OPC, MNT, DES",\n'
        '  "maintenance_action_code": "ISO 14224 code e.g. RPL, REP, OVH",\n'
        '  "detection_method_code": "ISO 14224 code e.g. MON, INS, PRD",\n'
        '  "hypothesis": ["string"], "root_causes": ["string"],\n'
        '  "contributing_factors": ["string"], "evidence_ids": ["string"],\n'
        '  "immediate_actions": ["string"], "pm_suggestions": ["string"],\n'
        '  "repair_plan": {"parts_list": [], "tools_required": [], "procedure_steps": [],\n'
        '    "estimated_duration_hrs": 0.0, "safety_requirements": [], "permit_type": "",\n'
        '    "spare_parts_cost_estimate": 0.0},\n'
        '  "confidence": 0.0\n'
        '}'
    )

    def _parse_structured(self, text: str) -> Dict[str, Any]:
        import json
        import re

        # Extract first JSON object if model wraps content
        m = re.search(r"\{[\s\S]*\}", text)
        payload = text if m is None else m.group(0)
        try:
            obj = json.loads(payload)
        except Exception:
            # Fallback minimal structure
            return {
                "title": "RCA Draft",
                "summary": text[:280],
                "hypothesis": [text[:400]],
                "root_causes": [text[:400]],
                "contributing_factors": [],
                "evidence_ids": [],
                "immediate_actions": [],
                "pm_suggestions": [],
                "repair_plan": {
                    "parts_list": [],
                    "tools_required": [],
                    "procedure_steps": [],
                    "estimated_duration_hrs": 0.0,
                    "safety_requirements": [],
                    "permit_type": "",
                    "spare_parts_cost_estimate": 0.0,
                },
                "confidence": 0.5,
            }
        # Fill missing keys with defaults
        defaults = {
            "title": "RCA Draft",
            "summary": "",
            "hypothesis": [],
            "root_causes": [],
            "contributing_factors": [],
            "evidence_ids": [],
            "immediate_actions": [],
            "pm_suggestions": [],
            "repair_plan": {
                "parts_list": [],
                "tools_required": [],
                "procedure_steps": [],
                "estimated_duration_hrs": 0.0,
                "safety_requirements": [],
                "permit_type": "",
                "spare_parts_cost_estimate": 0.0,
            },
            "confidence": 0.5,
        }
        for k, v in defaults.items():
            obj.setdefault(k, v)

        if not isinstance(obj.get("repair_plan"), dict):
            obj["repair_plan"] = defaults["repair_plan"].copy()
        else:
            rp_defaults = defaults["repair_plan"]
            for key, value in rp_defaults.items():
                obj["repair_plan"].setdefault(key, value)
        # Bound confidence
        try:
            obj["confidence"] = float(obj["confidence"])
            obj["confidence"] = (
                0.0
                if obj["confidence"] < 0
                else (1.0 if obj["confidence"] > 1 else obj["confidence"])
            )
        except Exception:
            obj["confidence"] = 0.5
        return obj
