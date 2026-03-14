import json
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.api.auth import require_role
from maintenance_intelligence.context.assembler import with_pg
from maintenance_intelligence.api.metrics import REGISTRY
from maintenance_intelligence.multitenancy import TenantContext
from prometheus_client import Counter

router = APIRouter(prefix="/api/v1/rca", tags=["rca"])
feedback_total = Counter("rca_feedback_total", "Total RCA feedback items", ["action"], registry=REGISTRY)

class FeedbackPayload(BaseModel):
    run_id: str = Field(..., description="Run id (event-level id in recommendation envelope)")
    recommendation_id: str = Field(..., description="Recommendation id")
    action: str = Field(..., description="accept | reject | edited")
    changes: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    user_id: Optional[str] = None
    asset_id: Optional[str] = None

@router.post("/feedback")
def submit_feedback(p: FeedbackPayload, access: TenantContext = Depends(require_role("operator"))):
    if p.action not in ("accept","reject","edited"):
        raise HTTPException(status_code=400, detail="Invalid action")
    s = Settings()
    conn = with_pg(s.pg_dsn)
    try:
        fid = "FB-" + uuid.uuid4().hex[:12]
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rca_feedback(id, run_id, recommendation_id, org_id, asset_id, action, changes, reason, user_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                """,
                (fid, p.run_id, p.recommendation_id, access.org_id, p.asset_id, p.action, json.dumps(p.changes) if p.changes else None, p.reason, p.user_id)
            )
        try:
            feedback_total.labels(action=p.action).inc()
        except Exception:
            pass
        return {"status":"ok","feedback_id":fid}
    finally:
        conn.close()