import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse

from maintenance_intelligence.api.middleware.identity import require_authenticated_identity
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.services.repair_plan_service import get_repair_plan, list_parts_for_plan

router = APIRouter(tags=["portal"])

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    items: List[str] = []
    for item in value:
        text = _as_text(item)
        if text is not None:
            items.append(text)
    return items


def _as_safe_text(value: Any, default: str = "") -> str:
    return _as_text(value) or default


def _sanitize_meta_value(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = _as_text(key)
            if key_text is None:
                continue
            normalized = _sanitize_meta_value(item)
            if normalized in (None, "", [], {}):
                continue
            cleaned[key_text] = normalized
        return cleaned

    if isinstance(value, (list, tuple, set)):
        items = [item for item in (_sanitize_meta_value(item) for item in value) if item not in (None, "", [], {})]
        return items

    text = _as_text(value)
    if text is not None:
        return text

    number = _as_number(value)
    if number is not None:
        return number

    return None


def _sanitize_context_meta(value: Any) -> Dict[str, Any]:
    cleaned = _sanitize_meta_value(value)
    return cleaned if isinstance(cleaned, dict) else {}


def _sanitize_model(value: Any) -> Dict[str, Any]:
    model = _as_dict(value)
    return {
        "name": _as_safe_text(model.get("name")),
        "version": _as_safe_text(model.get("version")),
        "latency_ms": _as_number(model.get("latency_ms")),
        "confidence": _as_number(model.get("confidence")),
    }


def _sanitize_structured(value: Any) -> Dict[str, Any]:
    structured = _as_dict(value)
    repair_plan = _sanitize_structured_repair_plan(structured.get("repair_plan"))
    sanitized = {
        "title": _as_safe_text(structured.get("title")),
        "summary": _as_safe_text(structured.get("summary")),
        "confidence": _as_number(structured.get("confidence")),
        "hypothesis": _as_string_list(structured.get("hypothesis")),
        "root_causes": _as_string_list(structured.get("root_causes")),
        "contributing_factors": _as_string_list(structured.get("contributing_factors")),
        "evidence_ids": _as_string_list(structured.get("evidence_ids")),
        "immediate_actions": _as_string_list(structured.get("immediate_actions")),
        "pm_suggestions": _as_string_list(structured.get("pm_suggestions")),
    }
    if _repair_plan_has_content(repair_plan):
        sanitized["repair_plan"] = repair_plan
    return sanitized


def _sanitize_repair_part(value: Any) -> Dict[str, Any]:
    part = _as_dict(value)
    return {
        "part_id": _as_safe_text(part.get("part_id")),
        "plan_id": _as_safe_text(part.get("plan_id")),
        "name": _as_safe_text(part.get("name")),
        "description": _as_safe_text(part.get("description")),
        "quantity": _as_number(part.get("quantity")),
        "unit": _as_safe_text(part.get("unit")),
        "metadata": _sanitize_context_meta(part.get("metadata")),
        "created_at": _as_safe_text(part.get("created_at")),
    }


def _sanitize_structured_part(value: Any) -> Dict[str, Any]:
    part = _as_dict(value)
    return {
        "part_no": _as_safe_text(part.get("part_no")),
        "description": _as_safe_text(part.get("description")),
        "qty": _as_number(part.get("qty")),
        "lead_time_days": _as_number(part.get("lead_time_days")),
    }


def _sanitize_structured_procedure_step(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        return {
            "seq": None,
            "action": _as_safe_text(value),
            "safety_note": "",
            "estimated_mins": None,
        }
    step = _as_dict(value)
    return {
        "seq": _as_number(step.get("seq")),
        "action": _as_safe_text(step.get("action")),
        "safety_note": _as_safe_text(step.get("safety_note")),
        "estimated_mins": _as_number(step.get("estimated_mins")),
    }


def _sanitize_structured_repair_plan(value: Any) -> Dict[str, Any]:
    repair_plan = _as_dict(value)
    parts_list = [_sanitize_structured_part(item) for item in repair_plan.get("parts_list") or [] if isinstance(item, dict)]
    procedure_steps = [_sanitize_structured_procedure_step(item) for item in repair_plan.get("procedure_steps") or []]
    return {
        "plan_id": _as_safe_text(repair_plan.get("plan_id")),
        "summary": _as_safe_text(repair_plan.get("summary")),
        "rationale": _as_safe_text(repair_plan.get("rationale")),
        "confidence": _as_number(repair_plan.get("confidence")),
        "status": _as_safe_text(repair_plan.get("status")),
        "parts_list": [item for item in parts_list if any(item.values())],
        "tools_required": _as_string_list(repair_plan.get("tools_required")),
        "procedure_steps": [item for item in procedure_steps if any(item.values())],
        "estimated_duration_hrs": _as_number(repair_plan.get("estimated_duration_hrs")),
        "safety_requirements": _as_string_list(repair_plan.get("safety_requirements")),
        "permit_type": _as_safe_text(repair_plan.get("permit_type")),
        "spare_parts_cost_estimate": _as_number(repair_plan.get("spare_parts_cost_estimate")),
    }


def _repair_plan_has_content(value: Dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        return False
    for item in value.values():
        if item not in (None, "", [], {}):
            return True
    return False


def _load_persisted_repair_plan(plan_id: str) -> Dict[str, Any]:
    try:
        settings = Settings()
        plan = get_repair_plan(settings.pg_dsn, plan_id)
        if not plan:
            return {"plan_id": plan_id}
        parts = list_parts_for_plan(settings.pg_dsn, plan_id)
        sanitized = {
            "plan_id": _as_safe_text(plan.get("plan_id")),
            "run_id": _as_safe_text(plan.get("run_id")),
            "recommendation_id": _as_safe_text(plan.get("recommendation_id")),
            "org_id": _as_safe_text(plan.get("org_id")),
            "asset_id": _as_safe_text(plan.get("asset_id")),
            "summary": _as_safe_text(plan.get("summary")),
            "rationale": _as_safe_text(plan.get("rationale")),
            "confidence": _as_number(plan.get("confidence")),
            "status": _as_safe_text(plan.get("status")),
            "created_at": _as_safe_text(plan.get("created_at")),
            "updated_at": _as_safe_text(plan.get("updated_at")),
            "parts": [_sanitize_repair_part(item) for item in parts],
        }
        return sanitized
    except Exception:
        return {
            "plan_id": plan_id,
            "load_error": "Repair plan lookup unavailable",
        }


def _extract_repair_plan(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    structured = _as_dict(payload.get("structured"))
    structured_plan = _sanitize_structured_repair_plan(structured.get("repair_plan"))
    plan_id = _as_safe_text(payload.get("repair_plan_id")) or structured_plan.get("plan_id")
    persisted_plan = _load_persisted_repair_plan(plan_id) if plan_id else {}
    merged = {
        "plan_id": plan_id or _as_safe_text(persisted_plan.get("plan_id")),
        "run_id": _as_safe_text(persisted_plan.get("run_id")),
        "recommendation_id": _as_safe_text(persisted_plan.get("recommendation_id")),
        "org_id": _as_safe_text(persisted_plan.get("org_id")),
        "asset_id": _as_safe_text(persisted_plan.get("asset_id")),
        "summary": structured_plan.get("summary") or _as_safe_text(persisted_plan.get("summary")),
        "rationale": structured_plan.get("rationale") or _as_safe_text(persisted_plan.get("rationale")),
        "confidence": structured_plan.get("confidence") if structured_plan.get("confidence") is not None else _as_number(persisted_plan.get("confidence")),
        "status": structured_plan.get("status") or _as_safe_text(persisted_plan.get("status")),
        "created_at": _as_safe_text(persisted_plan.get("created_at")),
        "updated_at": _as_safe_text(persisted_plan.get("updated_at")),
        "parts": [_sanitize_repair_part(item) for item in persisted_plan.get("parts") or [] if isinstance(item, dict)],
        "parts_list": structured_plan.get("parts_list") or [],
        "tools_required": structured_plan.get("tools_required") or [],
        "procedure_steps": structured_plan.get("procedure_steps") or [],
        "estimated_duration_hrs": structured_plan.get("estimated_duration_hrs"),
        "safety_requirements": structured_plan.get("safety_requirements") or [],
        "permit_type": structured_plan.get("permit_type"),
        "spare_parts_cost_estimate": structured_plan.get("spare_parts_cost_estimate"),
        "load_error": _as_safe_text(persisted_plan.get("load_error")),
    }
    return merged if _repair_plan_has_content(merged) else None


def _validate_run_id(run_id: str) -> str:
    candidate = run_id.strip()
    if not candidate or candidate != run_id or len(candidate) > 255 or any(ord(char) < 32 for char in candidate):
        raise HTTPException(status_code=400, detail="Invalid run id")
    return candidate


def _validate_asset_id(asset_id: str) -> str:
    candidate = asset_id.strip()
    if not candidate or candidate != asset_id or len(candidate) > 255 or any(ord(char) < 32 for char in candidate):
        raise HTTPException(status_code=400, detail="Invalid asset id")
    return candidate


def _require_read_access(request: Request) -> None:
    require_authenticated_identity(request, detail="Portal run data requires an authenticated identity")


def _portal_index_path() -> Path:
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="Portal assets are missing")
    return index_path


def _run_summary_root() -> Path:
    settings = Settings()
    return Path(settings.run_summary_dir).expanduser()


def _extract_run_summary(payload: Dict[str, Any], source_path: Path) -> Dict[str, Any]:
    structured = _sanitize_structured(payload.get("structured"))
    model = _sanitize_model(payload.get("model"))
    structured_repair_plan = structured.get("repair_plan") if isinstance(structured.get("repair_plan"), dict) else {}
    return {
        "run_id": _as_text(payload.get("run_id")) or source_path.stem,
        "status": _as_safe_text(payload.get("status"), "unknown"),
        "event_id": _as_safe_text(payload.get("event_id")),
        "recommendation_id": _as_safe_text(payload.get("recommendation_id")),
        "title": structured["title"],
        "summary": structured["summary"],
        "confidence": structured["confidence"],
        "hypothesis": structured["hypothesis"],
        "immediate_actions": structured["immediate_actions"],
        "pm_suggestions": structured["pm_suggestions"],
        "repair_plan_id": _as_safe_text(payload.get("repair_plan_id")) or _as_safe_text(structured_repair_plan.get("plan_id")),
        "model": model,
        "context_meta": _sanitize_context_meta(payload.get("context_meta")),
        "date": source_path.parent.name,
        "source_file": source_path.name,
        "updated_at": source_path.stat().st_mtime,
    }


def _load_run_payload(source_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with source_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _list_run_files(root: Path) -> List[Path]:
    if not root.exists() or not root.is_dir():
        return []
    return sorted(root.glob("*/*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def _find_latest_run_by_asset(root: Path, asset_id: str) -> Optional[Dict[str, Any]]:
    for path in _list_run_files(root):
        payload = _load_run_payload(path)
        if payload is None:
            continue
        context_meta = _sanitize_context_meta(payload.get("context_meta"))
        if _as_safe_text(context_meta.get("asset_id")) != asset_id:
            continue
        return _extract_run_summary(payload, path)
    return None


@router.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/portal", status_code=307)


@router.get("/portal", include_in_schema=False)
@router.get("/portal/", include_in_schema=False)
def portal_index():
    return FileResponse(_portal_index_path())


@router.get("/api/v1/portal/runs")
def recent_runs(request: Request, limit: int = Query(12, ge=1, le=50)) -> List[Dict[str, Any]]:
    _require_read_access(request)
    items: List[Dict[str, Any]] = []
    for path in _list_run_files(_run_summary_root()):
        payload = _load_run_payload(path)
        if payload is None:
            continue
        items.append(_extract_run_summary(payload, path))
        if len(items) >= limit:
            break
    return items


@router.get("/api/v1/portal/runs/latest")
def latest_run_for_asset(request: Request, asset_id: str = Query(..., min_length=1, description="Asset ID to resolve to the freshest run summary")) -> Dict[str, Any]:
    _require_read_access(request)
    resolved_asset_id = _validate_asset_id(asset_id)
    latest_run = _find_latest_run_by_asset(_run_summary_root(), resolved_asset_id)
    if latest_run is None:
        raise HTTPException(status_code=404, detail="Run summary not found for asset")
    return latest_run


@router.get("/api/v1/portal/runs/{run_id}")
def run_details(run_id: str, request: Request) -> Dict[str, Any]:
    _require_read_access(request)
    run_id = _validate_run_id(run_id)
    for path in _list_run_files(_run_summary_root()):
        if path.stem != run_id:
            continue
        payload = _load_run_payload(path)
        if payload is None:
            raise HTTPException(status_code=422, detail="Run summary is malformed")
        return {
            **_extract_run_summary(payload, path),
            "structured": _sanitize_structured(payload.get("structured")),
            "repair_plan": _extract_repair_plan(payload),
        }
    raise HTTPException(status_code=404, detail="Run summary not found")