import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse

from maintenance_intelligence.runner.config import Settings

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


def _portal_index_path() -> Path:
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="Portal assets are missing")
    return index_path


def _run_summary_root() -> Path:
    settings = Settings()
    return Path(settings.run_summary_dir).expanduser()


def _extract_run_summary(payload: Dict[str, Any], source_path: Path) -> Dict[str, Any]:
    structured = _as_dict(payload.get("structured"))
    model = _as_dict(payload.get("model"))
    return {
        "run_id": _as_text(payload.get("run_id")) or source_path.stem,
        "status": _as_text(payload.get("status")) or "unknown",
        "event_id": _as_text(payload.get("event_id")),
        "recommendation_id": _as_text(payload.get("recommendation_id")),
        "title": _as_text(structured.get("title")),
        "confidence": _as_number(structured.get("confidence")),
        "hypothesis": _as_string_list(structured.get("hypothesis")),
        "immediate_actions": _as_string_list(structured.get("immediate_actions")),
        "pm_suggestions": _as_string_list(structured.get("pm_suggestions")),
        "model": {
            "name": _as_text(model.get("name")),
            "version": _as_text(model.get("version")),
            "latency_ms": _as_number(model.get("latency_ms")),
            "confidence": _as_number(model.get("confidence")),
        },
        "context_meta": _as_dict(payload.get("context_meta")),
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


@router.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/portal", status_code=307)


@router.get("/portal", include_in_schema=False)
@router.get("/portal/", include_in_schema=False)
def portal_index():
    return FileResponse(_portal_index_path())


@router.get("/api/v1/portal/runs")
def recent_runs(limit: int = Query(12, ge=1, le=50)) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for path in _list_run_files(_run_summary_root()):
        payload = _load_run_payload(path)
        if payload is None:
            continue
        items.append(_extract_run_summary(payload, path))
        if len(items) >= limit:
            break
    return items


@router.get("/api/v1/portal/runs/{run_id}")
def run_details(run_id: str) -> Dict[str, Any]:
    for path in _list_run_files(_run_summary_root()):
        if path.stem != run_id:
            continue
        payload = _load_run_payload(path)
        if payload is None:
            raise HTTPException(status_code=422, detail="Run summary is malformed")
        return {
            **_extract_run_summary(payload, path),
            "structured": _as_dict(payload.get("structured")),
        }
    raise HTTPException(status_code=404, detail="Run summary not found")