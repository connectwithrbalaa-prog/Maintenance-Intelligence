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
        lines.append("Task: Draft an RCA hypothesis and recommended next actions for this alarm/anomaly.")
        lines.append(f"Event: {event}")
        lines.append(f"Context: {context}")
        lines.append("Output format:\\n- Title\\n- Hypothesis (2-4 bullets)\\n- Evidence to check (signals/WOs/docs)\\n- Immediate actions (1-3)\\n- Longer-term PM/design suggestions (1-2)")
        return "\\n".join(lines)
