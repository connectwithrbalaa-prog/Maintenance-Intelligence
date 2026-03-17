import os, time
from typing import Dict, Any
from loguru import logger
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

class GenAIGateway:
    def __init__(self, api_key: str, model: str, timeout_s: int = 25):
        self.model = model
        self.timeout_s = timeout_s
        if OpenAI is None:
            raise RuntimeError("openai package not installed")
        self.client = OpenAI(api_key=api_key)

    def call_rca(self, event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        prompt = self._build_prompt(event, context)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an industrial maintenance RCA assistant. Be concise and cite signals/WOs/docs when possible."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                timeout=self.timeout_s,
            )
            text = resp.choices[0].message.content.strip() if resp.choices else ""
            usage = getattr(resp, "usage", None)
            tokens = usage.total_tokens if usage else None
        except Exception as e:
            logger.error({"event":"genai.error","err":str(e)})
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

    
    def _build_prompt(self, event: Dict[str, Any], context: Dict[str, Any]) -> str:
        lines = []
        lines.append("You are an industrial maintenance RCA assistant. Respond with STRICT JSON only.")
        lines.append("Do NOT include markdown, backticks, or commentary — return ONLY the JSON object.")
        lines.append("Use this schema and fill every field; if unknown, produce your best estimate:")
        lines.append('\nSCHEMA (strict JSON; do not include extra keys):\n{\n  "title": "string",\n  "summary": "string",\n  "hypothesis": ["string", "..."],\n  "root_causes": ["string", "..."],\n  "contributing_factors": ["string", "..."],\n  "evidence_ids": ["string", "..."],\n  "immediate_actions": ["string", "..."],\n  "pm_suggestions": ["string", "..."],\n  "repair_plan": {\n    "parts_list": [{"part_no":"string","description":"string","qty":1,"lead_time_days":0}],\n    "tools_required": ["string", "..."],\n    "procedure_steps": [{"seq":1,"action":"string","safety_note":"string","estimated_mins":0}],\n    "estimated_duration_hrs": 0.0,\n    "safety_requirements": ["string", "..."],\n    "permit_type": "string",\n    "spare_parts_cost_estimate": 0.0\n  },\n  "confidence": 0.0\n}\n')
        lines.append("Event JSON:")
        lines.append(str(event))
        lines.append("Context JSON:")
        lines.append(str(context))
        return "\n".join(lines)

    def _parse_structured(self, text: str) -> Dict[str, Any]:
        import json, re
        # Extract first JSON object if model wraps content
        m = re.search(r'\{[\s\S]*\}', text)
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
                "confidence": 0.5
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
            "confidence": 0.5
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
            obj["confidence"] = 0.0 if obj["confidence"] < 0 else (1.0 if obj["confidence"] > 1 else obj["confidence"])
        except Exception:
            obj["confidence"] = 0.5
        return obj
