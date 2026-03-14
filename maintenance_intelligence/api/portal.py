from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(tags=["portal"])

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _portal_index_path() -> Path:
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="Portal assets are missing")
    return index_path


@router.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/portal", status_code=307)


@router.get("/portal", include_in_schema=False)
@router.get("/portal/", include_in_schema=False)
@router.get("/portal/pm-approvals", include_in_schema=False)
@router.get("/portal/pm-approvals/", include_in_schema=False)
def portal_index():
    return FileResponse(_portal_index_path())