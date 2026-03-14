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
        return {
            "text": text,
            "model_version": self.model,
            "tokens": tokens,
            "latency_ms": latency,
        }

    
    def _build_prompt(self, event: Dict[str, Any], context: Dict[str, Any]) -> str:
        lines = []
        lines.append("You are an industrial maintenance RCA assistant. Respond with STRICT JSON only.")
        lines.append("Do NOT include markdown, backticks, or commentary — return ONLY the JSON object.")
        lines.append("Use this schema and fill every field; if unknown, produce your best estimate:")
        lines.append('\nSCHEMA (strict JSON; do not include extra keys):\n{\n  "title": "string",\n  "hypothesis": ["string", "..."],\n  "evidence_ids": ["string", "..."],  // IDs from signals/doc chunks/WOs\n  "immediate_actions": ["string", "..."],\n  "pm_suggestions": ["string", "..."],\n  "confidence": 0.0  // 0..1\n}\n')
        lines.append("Event JSON:")
        lines.append(str(event))
        lines.append("Context JSON:")
        lines.append(str(context))
        return "\n".join(lines)

        lines.append("Task: Draft an RCA hypothesis and recommended next actions for this alarm/anomaly.")
        lines.append(f"Event: {event}")
        lines.append(f"Context: {context}")
        lines.append("Output format:\\n- Title\\n- Hypothesis (2-4 bullets)\\n- Evidence to check (signals/WOs/docs)\\n- Immediate actions (1-3)\\n- Longer-term PM/design suggestions (1-2)")
        return "\\n".join(lines)

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
