import re
from typing import Any, Dict, List, Optional

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


def _normalize_doc_chunks(rows: List[Any]) -> List[Dict[str, Any]]:
    return [{"chunk_id": row[0], "title": row[1]} for row in rows if row]


def _flatten_detail_value(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        parts: List[str] = []
        for key in sorted(value):
            parts.extend(_flatten_detail_value(value[key]))
        return parts
    if isinstance(value, (list, tuple, set)):
        parts: List[str] = []
        values = sorted(value, key=str) if isinstance(value, set) else value
        for item in values:
            parts.extend(_flatten_detail_value(item))
        return parts
    return [str(value)]


def _build_rag_query(event: Dict[str, Any]) -> str:
    event_details = event.get("details", {})
    event_kind = event.get("kind", "")
    event_summary = event.get("summary", "")
    detail_values = " ".join(
        part for key in sorted(event_details) for part in _flatten_detail_value(event_details[key])
    )
    return " ".join(part for part in [event_kind, event_summary, detail_values] if part).strip()


def _tokenize_fallback_query(query: str) -> List[str]:
    return [token for token in re.sub(r"[^\w\s]", " ", query.lower()).split() if token]


def _score_fallback_doc_chunk(row: Any, query_terms: List[str]) -> tuple[int, float, str]:
    title = str(row[1] or "")
    content = str(row[2] or "") if len(row) > 2 else ""
    title_text = title.lower()
    content_text = content.lower()

    if not query_terms:
        created_at = row[3].timestamp() if len(row) > 3 and row[3] else 0.0
        return (0, created_at, str(row[0]))

    title_hits = sum(title_text.count(term) for term in query_terms)
    content_hits = sum(content_text.count(term) for term in query_terms)
    lexical_score = (title_hits * 3) + content_hits
    created_at = row[3].timestamp() if len(row) > 3 and row[3] else 0.0
    return (lexical_score, created_at, str(row[0]))


def _rank_fallback_doc_chunks(rows: List[Any], query: str, limit: int = 3) -> List[Dict[str, Any]]:
    query_terms = _tokenize_fallback_query(query)

    def sort_key(row: Any) -> tuple[int, float, str]:
        lexical_score, created_at, chunk_id = _score_fallback_doc_chunk(row, query_terms)
        return (-lexical_score, -created_at, chunk_id)

    ranked_rows = sorted(rows, key=sort_key)
    return _normalize_doc_chunks(ranked_rows[:limit])


def get_event_context(
    event: Dict[str, Any], settings: Optional[Settings] = None, org_id: Optional[str] = None
) -> Dict[str, Any]:
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
    out: Dict[str, Any] = {
        "asset_id": asset_id,
        "last_wo_titles": [],
        "signal_summary": {},
        "doc_chunks": [],
    }
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
                    """,
                    (asset_id, org_scope_enabled(settings), effective_org_id),
                )
                rows = cur.fetchall()
                out["last_wo_titles"] = [r[0] for r in rows if r and r[0]]
        except Exception as e:
            logger.debug({"event": "ctx.wo.skip", "err": str(e)})

        # signal summary: recent rollups and anomalies
        try:
            with conn, conn.cursor() as cur:
                # Get latest rollups for each signal type
                cur.execute(
                    """
                    SELECT signal_type, period, mean_value, min_value, max_value, anomaly_flags
                    FROM signal_rollups
                    WHERE asset_id = %s AND (%s = FALSE OR org_id = %s) AND end_time >= NOW() - INTERVAL '24 hours'
                    ORDER BY end_time DESC
                    LIMIT 10
                """,
                    (asset_id, org_scope_enabled(settings), effective_org_id),
                )
                rollups = cur.fetchall()
                out["signal_rollups"] = [
                    {
                        "signal_type": r[0],
                        "period": r[1],
                        "mean": r[2],
                        "min": r[3],
                        "max": r[4],
                        "anomalies": r[5] or {},
                    }
                    for r in rollups
                ]

                # Get recent signals with anomaly flags
                cur.execute(
                    """
                    SELECT signal_id, signal_type, value, timestamp, metadata
                    FROM signals
                    WHERE asset_id = %s AND (%s = FALSE OR org_id = %s) AND timestamp >= NOW() - INTERVAL '1 hour'
                    ORDER BY timestamp DESC
                    LIMIT 20
                """,
                    (asset_id, org_scope_enabled(settings), effective_org_id),
                )
                signals = cur.fetchall()
                out["recent_signals"] = [
                    {
                        "signal_id": r[0],
                        "signal_type": r[1],
                        "value": r[2],
                        "timestamp": r[3].isoformat() if r[3] else None,
                        "metadata": r[4] or {},
                    }
                    for r in signals
                ]
        except Exception as e:
            logger.debug({"event": "ctx.signals.skip", "err": str(e)})
            out["signal_rollups"] = []
            out["recent_signals"] = []

        # doc chunks via hybrid retrieval (BM25 + vector)
        try:
            from maintenance_intelligence.rag.retrieval import HybridRetriever

            query = _build_rag_query(event)

            retriever = HybridRetriever(settings.pg_dsn)
            chunks = retriever.retrieve(
                query, asset_id, limit=5, token_budget=2000, org_id=effective_org_id
            )
            out["doc_chunks"] = [{"chunk_id": c["chunk_id"], "title": c["title"]} for c in chunks]
        except Exception as e:
            logger.debug({"event": "ctx.hybrid_rag.skip", "err": str(e)})
            try:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT chunk_id, title, content, created_at FROM doc_chunks
                        WHERE asset_id = %s
                        AND (%s = FALSE OR org_id = %s)
                        ORDER BY created_at DESC, chunk_id ASC
                        LIMIT 25
                        """,
                        (asset_id, org_scope_enabled(settings), effective_org_id),
                    )
                    out["doc_chunks"] = _rank_fallback_doc_chunks(cur.fetchall(), query)
            except Exception as e2:
                logger.debug({"event": "ctx.docs.skip", "err": str(e2)})
                out["doc_chunks"] = []

    except Exception as e:
        logger.debug({"event": "ctx.error", "err": str(e)})
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
    return out
