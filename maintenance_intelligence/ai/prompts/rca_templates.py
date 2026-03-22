"""ISO 14224–aligned prompt templates for structured RCA.

These templates use ISO terminology and canonical fields instead of
raw CMMS codes. They are designed to produce structured output that
maps directly back to the canonical failure event schema.
"""

from __future__ import annotations

from typing import Optional

from maintenance_intelligence.ai.rag.structured_retriever import RCAContext


SYSTEM_PROMPT = """You are a reliability engineer performing root cause analysis on upstream oil and gas equipment. You follow ISO 14224 classification standards for failure analysis.

When analyzing failures:
1. Classify the failure mode using ISO 14224 Annex B codes (e.g., VIB for vibration, ELP for external leakage, FTS for failure to start).
2. Identify the failure mechanism (e.g., WEA for wear, COR for corrosion, FAT for fatigue).
3. Determine the failure cause category (e.g., OPC for operating conditions, MNT for maintenance-related, DES for design-related).
4. Recommend maintenance actions using ISO codes (e.g., REP for repair, RPL for replace, OVH for overhaul).
5. Specify the detection method (e.g., MON for continuous monitoring, INS for inspection, PRD for production interference).

Always reference the equipment hierarchy (site → facility → system → equipment → subunit → component) when localizing the failure.

Respond with structured JSON output matching this schema:
{
  "title": "One-line summary of the failure",
  "failure_mode_code": "ISO 14224 code",
  "failure_mechanism_code": "ISO 14224 code",
  "failure_cause_code": "ISO 14224 code",
  "maintenance_action_code": "ISO 14224 code",
  "detection_method_code": "ISO 14224 code",
  "hypothesis": ["List of probable cause hypotheses"],
  "root_causes": ["Identified root causes"],
  "contributing_factors": ["Contributing factors"],
  "immediate_actions": ["Immediate maintenance actions"],
  "pm_suggestions": ["Planned maintenance recommendations"],
  "confidence": 0.0 to 1.0,
  "repair_plan": {
    "summary": "Repair plan summary",
    "procedure_steps": [{"seq": 1, "action": "Step description", "safety_note": "Safety requirement", "estimated_mins": 30}],
    "parts_list": [{"part_no": "SKF-7320", "description": "Angular contact bearing", "qty": 2}],
    "tools_required": ["Tool list"],
    "safety_requirements": ["Safety requirements"],
    "estimated_duration_hrs": 8,
    "permit_type": "Hot work / confined space / LOTO"
  }
}"""


def build_rca_prompt(
    event_summary: str,
    context: Optional[RCAContext] = None,
    *,
    asset_id: Optional[str] = None,
    event_kind: Optional[str] = None,
    severity: Optional[str] = None,
) -> str:
    """Build a structured RCA prompt with ISO 14224 context.

    Args:
        event_summary: The alarm/anomaly description
        context: Assembled RCA context from structured retrievers
        asset_id: Equipment tag or asset reference
        event_kind: alarm, anomaly, measurement
        severity: critical, high, medium, low
    """
    parts = [f"## Event to analyze\n{event_summary}"]

    if asset_id:
        parts.append(f"Asset: {asset_id}")
    if event_kind:
        parts.append(f"Event type: {event_kind}")
    if severity:
        parts.append(f"Severity: {severity}")

    if context:
        parts.append(context.to_prompt_text())

    parts.append(
        "\n## Instructions\n"
        "Analyze this event using ISO 14224 failure classification. "
        "Provide structured root cause analysis with ISO-coded failure mode, mechanism, "
        "cause, recommended maintenance action, and detection method. "
        "Include a repair plan with procedure steps, parts, tools, and safety requirements. "
        "Reference the equipment hierarchy and past failure patterns in your reasoning."
    )

    return "\n\n".join(parts)


def build_pm_optimization_prompt(
    equipment_context: str,
    failure_history_text: str,
    reliability_text: str,
) -> str:
    """Build a prompt for preventive maintenance optimization."""
    return f"""## Equipment context
{equipment_context}

## Failure history
{failure_history_text}

## Current reliability metrics
{reliability_text}

## Instructions
Based on the failure history and reliability metrics for this equipment:
1. Identify the dominant failure modes and mechanisms.
2. Assess whether the current PM interval is adequate or should be adjusted.
3. Recommend specific condition-based monitoring parameters and thresholds.
4. Suggest any design or operational changes to reduce failure frequency.
5. Estimate the impact on MTBF and availability if recommendations are implemented.

Use ISO 14224 terminology for all failure classifications and maintenance actions."""
