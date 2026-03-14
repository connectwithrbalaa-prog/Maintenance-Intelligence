import datetime as dt
from typing import Dict, Any, List, Optional
import psycopg2
from loguru import logger
from maintenance_intelligence.multitenancy import org_scope_enabled, resolve_org_id
from maintenance_intelligence.runner.config import Settings

def with_pg(dsn: str):
    import time
    last_error = None
    for _ in range(3):
        try:
            return psycopg2.connect(dsn, connect_timeout=2)
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise last_error

def get_event_context(event: Dict[str, Any], settings: Optional[Settings] = None, org_id: Optional[str] = None) -> Dict[str, Any]:
    """
    MVP bootstrap context assembly.
    - last_wo_titles: last few WOs for the asset (90d)
    - signal_summary: stub (placeholder)
    - doc_chunks: stub (assumes optional doc_chunks table later)
    Returns empty lists gracefully if tables not present.
    """
    settings = settings or Settings()
    asset_id = event.get("asset_id")
    effective_org_id = resolve_org_id(settings, org_id or event.get("org_id"))
    out: Dict[str, Any] = {"asset_id": asset_id, "last_wo_titles": [], "signal_summary": {}, "doc_chunks": []}
    conn = None
    try:
        conn = with_pg(settings.pg_dsn)
        # last few WOs (if table exists)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT title FROM workorders
                    WHERE asset_id = %s AND (NOW() - INTERVAL '90 days') < NOW()
                    AND (%s = FALSE OR org_id = %s)
                    ORDER BY RANDOM() LIMIT 5
                    """, (asset_id, org_scope_enabled(settings), effective_org_id)
                )
                rows = cur.fetchall()
                out["last_wo_titles"] = [r[0] for r in rows if r and r[0]]
        except Exception as e:
            logger.debug({"event":"ctx.wo.skip","err":str(e)})

        # signal summary: recent rollups and anomalies
        try:
            with conn, conn.cursor() as cur:
                # Get latest rollups for each signal type
                cur.execute("""
                    SELECT signal_type, period, mean_value, min_value, max_value, anomaly_flags
                    FROM signal_rollups
                    WHERE asset_id = %s AND end_time >= NOW() - INTERVAL '24 hours'
                    ORDER BY end_time DESC
                    LIMIT 10
                """, (asset_id,))
                rollups = cur.fetchall()
                out["signal_rollups"] = [
                    {
                        "signal_type": r[0],
                        "period": r[1],
                        "mean": r[2],
                        "min": r[3],
                        "max": r[4],
                        "anomalies": r[5] or {}
                    } for r in rollups
                ]

                # Get recent signals with anomaly flags
                cur.execute("""
                    SELECT signal_id, signal_type, value, timestamp, metadata
                    FROM signals
                    WHERE asset_id = %s AND timestamp >= NOW() - INTERVAL '1 hour'
                    ORDER BY timestamp DESC
                    LIMIT 20
                """, (asset_id,))
                signals = cur.fetchall()
                out["recent_signals"] = [
                    {
                        "signal_id": r[0],
                        "signal_type": r[1],
                        "value": r[2],
                        "timestamp": r[3].isoformat() if r[3] else None,
                        "metadata": r[4] or {}
                    } for r in signals
                ]
        except Exception as e:
            logger.debug({"event":"ctx.signals.skip","err":str(e)})
            out["signal_rollups"] = []
            out["recent_signals"] = []

        # doc chunks via hybrid retrieval (BM25 + vector)
        try:
            from maintenance_intelligence.rag.retrieval import HybridRetriever
            # Create a query from event details for better retrieval
            event_details = event.get("details", {})
            event_kind = event.get("kind", "")
            event_summary = event.get("summary", "")
            query = f"{event_kind} {event_summary} {' '.join(str(v) for v in event_details.values())}"

            retriever = HybridRetriever(settings.pg_dsn)
            chunks = retriever.retrieve(query, asset_id, limit=5, token_budget=2000, org_id=effective_org_id)
            out["doc_chunks"] = [{"chunk_id": c["chunk_id"], "title": c["title"]} for c in chunks]
        except Exception as e:
            logger.debug({"event":"ctx.hybrid_rag.skip","err":str(e)})
            # Fallback to random selection
            try:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT chunk_id, title FROM doc_chunks
                        WHERE asset_id = %s
                        AND (%s = FALSE OR org_id = %s)
                        ORDER BY RANDOM()
                        LIMIT 3
                        """, (asset_id, org_scope_enabled(settings), effective_org_id)
                    )
                    rows = cur.fetchall()
                    out["doc_chunks"] = [{"chunk_id": r[0], "title": r[1]} for r in rows if r]
            except Exception as e2:
                logger.debug({"event":"ctx.docs.skip","err":str(e2)})
                out["doc_chunks"] = []


    except Exception as e:
        logger.debug({"event":"ctx.error","err":str(e)})
    finally:
        try:
            if conn: conn.close()
        except Exception:
            pass
    return out
