import datetime as dt
from typing import Dict, Any, List, Optional
import psycopg2
from loguru import logger
from maintenance_intelligence.runner.config import Settings

def with_pg(dsn: str):
    import time
    while True:
        try:
            return psycopg2.connect(dsn)
        except Exception:
            time.sleep(1)

def get_event_context(event: Dict[str, Any], settings: Optional[Settings] = None) -> Dict[str, Any]:
    """
    MVP bootstrap context assembly.
    - last_wo_titles: last few WOs for the asset (90d)
    - signal_summary: stub (placeholder)
    - doc_chunks: stub (assumes optional doc_chunks table later)
    Returns empty lists gracefully if tables not present.
    """
    settings = settings or Settings()
    asset_id = event.get("asset_id")
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
                    ORDER BY RANDOM() LIMIT 5
                    """, (asset_id,)
                )
                rows = cur.fetchall()
                out["last_wo_titles"] = [r[0] for r in rows if r and r[0]]
        except Exception as e:
            logger.debug({"event":"ctx.wo.skip","err":str(e)})

        # signal summary stub (extend via real signals later)
        out["signal_summary"] = {"note": "MVP stub; add rolling means/min/max from measurements"}

        # doc chunks stub (if doc_chunks table exists)
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT chunk_id, title FROM doc_chunks
                    WHERE asset_id = %s
                    ORDER BY RANDOM()
                    LIMIT 3
                    """, (asset_id,)
                )
                rows = cur.fetchall()
                out["doc_chunks"] = [{"chunk_id": r[0], "title": r[1]} for r in rows if r]
        except Exception as e:
            logger.debug({"event":"ctx.docs.skip","err":str(e)})
        # doc chunks via pgvector (if available)
        try:
            with conn, conn.cursor() as cur:
                # If pgvector/embedding not present, this will error and fall back
                cur.execute(
                    """
                    SELECT chunk_id, title
                    FROM doc_chunks
                    WHERE asset_id = %s
                    ORDER BY embedding <-> (SELECT embedding FROM doc_chunks WHERE asset_id = %s LIMIT 1)
                    LIMIT 3
                    """,
                    (asset_id, asset_id)
                )
                rows = cur.fetchall()
                out["doc_chunks"] = [{"chunk_id": r[0], "title": r[1]} for r in rows if r]
        except Exception as e:
            # Keep prior stub/random fallback if vector unavailable
            pass


    except Exception as e:
        logger.debug({"event":"ctx.error","err":str(e)})
    finally:
        try:
            if conn: conn.close()
        except Exception:
            pass
    return out
