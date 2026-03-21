import re
from typing import Dict, Any, List, Optional
import psycopg2
from loguru import logger
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


def _normalize_wo_titles(rows: List[Any]) -> List[str]:
    return [row[0] for row in rows if row and row[0]]


def _normalize_signal_rollups(rows: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "signal_type": row[0],
            "period": row[1],
            "mean": row[2],
            "min": row[3],
            "max": row[4],
            "anomalies": row[5] or {},
        }
        for row in rows
    ]


def _normalize_recent_signals(rows: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "signal_id": row[0],
            "signal_type": row[1],
            "value": row[2],
            "timestamp": row[3].isoformat() if row[3] else None,
            "metadata": row[4] or {},
        }
        for row in rows
    ]


def _normalize_doc_chunks(
    rows: List[Any], current_asset_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        row_asset_id = row[3] if len(row) > 3 else None
        source = row[4] if len(row) > 4 else None
        chunks.append(
            {
                "chunk_id": row[0],
                "title": row[1],
                "asset_id": row_asset_id,
                "source": source,
                "org_id": None,
                "site_id": None,
                "asset_class": None,
                "source_scope": (
                    "local" if not current_asset_id or row_asset_id == current_asset_id else "fleet"
                ),
            }
        )
    return chunks


def _tokenize_fallback_query(query: str) -> List[str]:
    return [token for token in re.sub(r"[^\w\s]", " ", query.lower()).split() if token]


def _score_fallback_doc_chunk(
    row: Any, query_terms: List[str], current_asset_id: Optional[str] = None
) -> tuple[int, int, float, str]:
    title = str(row[1] or "")
    content = str(row[2] or "") if len(row) > 2 else ""
    title_text = title.lower()
    content_text = content.lower()

    if not query_terms:
        created_at = row[5].timestamp() if len(row) > 5 and row[5] else 0.0
        locality = 0 if not current_asset_id or (len(row) > 3 and row[3] == current_asset_id) else 1
        return (0, locality, created_at, str(row[0]))

    title_hits = sum(title_text.count(term) for term in query_terms)
    content_hits = sum(content_text.count(term) for term in query_terms)
    lexical_score = (title_hits * 3) + content_hits
    created_at = row[5].timestamp() if len(row) > 5 and row[5] else 0.0
    locality = 0 if not current_asset_id or (len(row) > 3 and row[3] == current_asset_id) else 1
    return (lexical_score, locality, created_at, str(row[0]))


def _rank_fallback_doc_chunks(
    rows: List[Any], query: str, current_asset_id: Optional[str] = None, limit: int = 3
) -> List[Dict[str, Any]]:
    query_terms = _tokenize_fallback_query(query)

    def sort_key(row: Any) -> tuple[int, int, float, str]:
        lexical_score, locality, created_at, chunk_id = _score_fallback_doc_chunk(
            row, query_terms, current_asset_id
        )
        return (-lexical_score, locality, -created_at, chunk_id)

    ranked_rows = sorted(
        rows,
        key=sort_key,
    )
    return _normalize_doc_chunks(ranked_rows[:limit], current_asset_id)


def _summarize_fleet_doc_chunks(
    asset_id: Optional[str], doc_chunks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    external_chunks = [chunk for chunk in doc_chunks if chunk.get("source_scope") == "fleet"]
    referenced_asset_ids = sorted(
        {str(chunk.get("asset_id")) for chunk in external_chunks if chunk.get("asset_id")}
    )
    referenced_sources = sorted(
        {str(chunk.get("source")) for chunk in external_chunks if chunk.get("source")}
    )
    return {
        "external_ref_count": len(external_chunks),
        "referenced_asset_ids": referenced_asset_ids,
        "referenced_sources": referenced_sources,
        "current_asset_id": asset_id,
    }


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


def _fetch_last_wo_titles(conn, asset_id: Optional[str]) -> List[str]:
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT title FROM workorders
            WHERE asset_id = %s
            ORDER BY COALESCE(metadata->>'created_at', '') DESC, wo_id DESC
            LIMIT 5
            """,
            (asset_id,),
        )
        return _normalize_wo_titles(cur.fetchall())


def _fetch_signal_context(conn, asset_id: Optional[str]) -> Dict[str, List[Dict[str, Any]]]:
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT signal_type, period, mean_value, min_value, max_value, anomaly_flags
            FROM signal_rollups
            WHERE asset_id = %s AND end_time >= NOW() - INTERVAL '24 hours'
            ORDER BY end_time DESC, signal_type ASC, period ASC
            LIMIT 10
            """,
            (asset_id,),
        )
        rollups = _normalize_signal_rollups(cur.fetchall())

        cur.execute(
            """
            SELECT signal_id, signal_type, value, timestamp, metadata
            FROM signals
            WHERE asset_id = %s AND timestamp >= NOW() - INTERVAL '1 hour'
            ORDER BY timestamp DESC, signal_id ASC
            LIMIT 20
            """,
            (asset_id,),
        )
        recent_signals = _normalize_recent_signals(cur.fetchall())

    return {"signal_rollups": rollups, "recent_signals": recent_signals}


def _fetch_fallback_doc_chunks(
    conn, asset_id: Optional[str], query: str, fleet_wide: bool = False
) -> List[Dict[str, Any]]:
    with conn, conn.cursor() as cur:
        if asset_id and not fleet_wide:
            cur.execute(
                """
                SELECT chunk_id, title, content, asset_id, source, created_at FROM doc_chunks
                WHERE asset_id = %s
                ORDER BY created_at DESC, chunk_id ASC
                LIMIT 25
                """,
                (asset_id,),
            )
        else:
            cur.execute("""
                SELECT chunk_id, title, content, asset_id, source, created_at FROM doc_chunks
                ORDER BY created_at DESC, chunk_id ASC
                LIMIT 50
                """)
        return _rank_fallback_doc_chunks(cur.fetchall(), query, asset_id)


def _fetch_doc_chunks(
    conn,
    asset_id: Optional[str],
    query: str,
    dsn: str,
    retriever_cls=None,
    fleet_wide: bool = False,
) -> List[Dict[str, Any]]:
    if retriever_cls is None:
        from maintenance_intelligence.rag.retrieval import HybridRetriever

        retriever_cls = HybridRetriever

    try:
        retriever = retriever_cls(dsn)
        chunks = retriever.retrieve(
            query, asset_id, limit=5, token_budget=2000, fleet_wide=fleet_wide
        )
        return [
            {
                "chunk_id": chunk["chunk_id"],
                "title": chunk["title"],
                "asset_id": chunk.get("asset_id"),
                "source": chunk.get("source"),
                "org_id": chunk.get("org_id"),
                "site_id": chunk.get("site_id"),
                "asset_class": chunk.get("asset_class"),
                "source_scope": chunk.get("source_scope", "local"),
            }
            for chunk in chunks
        ]
    except Exception as exc:
        logger.debug({"event": "ctx.hybrid_rag.skip", "err": str(exc)})
        return _fetch_fallback_doc_chunks(conn, asset_id, query, fleet_wide=fleet_wide)


def get_event_context(
    event: Dict[str, Any],
    settings: Optional[Settings] = None,
    connection_factory=with_pg,
    retriever_cls=None,
    fleet_wide: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    MVP bootstrap context assembly.
    - last_wo_titles: last few WOs for the asset (90d)
    - signal_summary: stub (placeholder)
    - doc_chunks: stub (assumes optional doc_chunks table later)
    Returns empty lists gracefully if tables not present.
    """
    settings = settings or Settings()
    fleet_wide = settings.rca_fleet_wide_context if fleet_wide is None else fleet_wide
    asset_id = event.get("asset_id")
    out: Dict[str, Any] = {
        "asset_id": asset_id,
        "last_wo_titles": [],
        "signal_summary": {},
        "signal_rollups": [],
        "recent_signals": [],
        "doc_chunks": [],
        "context_scope": "local",
        "fleet_context_summary": {
            "external_ref_count": 0,
            "referenced_asset_ids": [],
            "referenced_sources": [],
            "current_asset_id": asset_id,
        },
    }
    conn = None
    try:
        conn = connection_factory(settings.pg_dsn)
        # last few WOs (if table exists)
        try:
            out["last_wo_titles"] = _fetch_last_wo_titles(conn, asset_id)
        except Exception as e:
            logger.debug({"event": "ctx.wo.skip", "err": str(e)})

        # signal summary: recent rollups and anomalies
        try:
            out.update(_fetch_signal_context(conn, asset_id))
        except Exception as e:
            logger.debug({"event": "ctx.signals.skip", "err": str(e)})
            out["signal_rollups"] = []
            out["recent_signals"] = []

        # doc chunks via hybrid retrieval (BM25 + vector)
        try:
            query = _build_rag_query(event)
            out["doc_chunks"] = _fetch_doc_chunks(
                conn,
                asset_id,
                query,
                settings.pg_dsn,
                retriever_cls=retriever_cls,
                fleet_wide=fleet_wide,
            )
            out["fleet_context_summary"] = _summarize_fleet_doc_chunks(asset_id, out["doc_chunks"])
            out["context_scope"] = (
                "local+fleet" if out["fleet_context_summary"]["external_ref_count"] else "local"
            )
        except Exception as e:
            logger.debug({"event": "ctx.docs.skip", "err": str(e)})
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
