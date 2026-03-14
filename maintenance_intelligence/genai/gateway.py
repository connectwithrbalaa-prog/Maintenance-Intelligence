import time
from typing import Any, Dict

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

    def call_rca(self, event: Dict[str, Any], context: Dict[str, Any], prompt_selection: Dict[str, Any] | None = None) -> Dict[str, Any]:
        t0 = time.time()
        system_prompt, prompt = self._build_prompt(event, context, prompt_selection=prompt_selection)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
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
        return {
            "text": text,
            "model_version": self.model,
            "tokens": tokens,
            "latency_ms": latency,
            "structured": self._parse_structured(text),
            "prompt_id": (prompt_selection or {}).get("prompt_id"),
        }

    def _build_prompt(self, event: Dict[str, Any], context: Dict[str, Any], prompt_selection: Dict[str, Any] | None = None) -> tuple[str, str]:
        default_system = "You are an industrial maintenance RCA assistant. Respond with strict JSON only."
        default_user = (
            "Use this schema and fill every field; if unknown, produce your best estimate:\n"
            '{{"title":"string","hypothesis":["string"],"evidence_ids":["string"],'
            '"immediate_actions":["string"],"pm_suggestions":["string"],"confidence":0.0}}\n'
            "Event JSON:\n{event_json}\n"
            "Context JSON:\n{context_json}"
        )
        prompt_selection = prompt_selection or {}
        system_prompt = prompt_selection.get("system_prompt") or default_system
        user_template = prompt_selection.get("user_prompt_template") or default_user
        prompt = user_template.format(
            event_json=str(event),
            context_json=str(context),
            asset_id=event.get("asset_id"),
            severity=event.get("severity"),
            kind=event.get("kind"),
        )
        return system_prompt, prompt

    def _parse_structured(self, text: str) -> Dict[str, Any]:
        import json
        import re
        # Extract first JSON object if model wraps content
        m = re.search(r'\{[\s\S]*\}', text)
        payload = text if m is None else m.group(0)
        try:
            obj = json.loads(payload)
        except Exception:
            # Fallback minimal structure
            return {
                "title": "RCA Draft",
                "hypothesis": [text[:400]],
                "evidence_ids": [],
                "immediate_actions": [],
                "pm_suggestions": [],
                "confidence": 0.5
            }
        # Fill missing keys with defaults
        defaults = {
            "title": "RCA Draft",
            "hypothesis": [],
            "evidence_ids": [],
            "immediate_actions": [],
            "pm_suggestions": [],
            "confidence": 0.5
        }
        for k, v in defaults.items():
            obj.setdefault(k, v)
        # Bound confidence
        try:
            obj["confidence"] = float(obj["confidence"])
            obj["confidence"] = 0.0 if obj["confidence"] < 0 else (1.0 if obj["confidence"] > 1 else obj["confidence"])
        except Exception:
            obj["confidence"] = 0.5
        return obj
