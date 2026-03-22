from fastapi import APIRouter, HTTPException, Query, Request
from maintenance_intelligence.api.middleware.identity import (
    require_authenticated_identity,
    require_identity_scope,
)
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.context.assembler import with_pg

router = APIRouter()


def _load_asset_scope(conn, asset_id: str) -> dict[str, str | None]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT org_id
            FROM events
            WHERE asset_id = %s
            ORDER BY occurred_at DESC
            LIMIT 1
        """,
            (asset_id,),
        )
        row = cur.fetchone()
    return {"org_id": row[0] if row else None}


@router.get("/api/v1/signals/summary")
async def get_signals_summary(
    request: Request,
    asset_id: str = Query(..., description="Asset ID to get signals for"),
    limit: int = Query(10, description="Max number of signals to return"),
):
    """Get recent signals and rollups for an asset."""
    require_authenticated_identity(
        request, detail="Signal summaries require an authenticated identity"
    )
    settings = Settings()
    conn = None
    try:
        conn = with_pg(settings.pg_dsn)
        with conn, conn.cursor() as cur:
            asset_scope = _load_asset_scope(conn, asset_id)
            if asset_scope.get("org_id"):
                require_identity_scope(
                    request,
                    org_id=asset_scope.get("org_id"),
                    detail="Signal scope does not match authenticated tenant",
                )

            # Get recent signals
            cur.execute(
                """
                SELECT signal_id, signal_type, value, unit, timestamp, metadata
                FROM signals
                WHERE asset_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """,
                (asset_id, limit),
            )
            signals = cur.fetchall()

            # Get latest rollups
            cur.execute(
                """
                SELECT signal_type, period, mean_value, min_value, max_value, anomaly_flags, end_time
                FROM signal_rollups
                WHERE asset_id = %s
                ORDER BY end_time DESC
                LIMIT 20
            """,
                (asset_id,),
            )
            rollups = cur.fetchall()

        return {
            "asset_id": asset_id,
            "recent_signals": [
                {
                    "signal_id": s[0],
                    "signal_type": s[1],
                    "value": s[2],
                    "unit": s[3],
                    "timestamp": s[4].isoformat() if s[4] else None,
                    "metadata": s[5] or {},
                }
                for s in signals
            ],
            "rollups": [
                {
                    "signal_type": r[0],
                    "period": r[1],
                    "mean": r[2],
                    "min": r[3],
                    "max": r[4],
                    "anomalies": r[5] or {},
                    "end_time": r[6].isoformat() if r[6] else None,
                }
                for r in rollups
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
