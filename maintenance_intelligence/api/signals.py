from fastapi import APIRouter, HTTPException, Query
from maintenance_intelligence.runner.config import Settings
from maintenance_intelligence.context.assembler import with_pg

router = APIRouter()


@router.get("/api/v1/signals/summary")
async def get_signals_summary(
    asset_id: str = Query(..., description="Asset ID to get signals for"),
    limit: int = Query(10, description="Max number of signals to return"),
):
    """Get recent signals and rollups for an asset."""
    settings = Settings()
    try:
        conn = with_pg(settings.pg_dsn)
        with conn, conn.cursor() as cur:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
