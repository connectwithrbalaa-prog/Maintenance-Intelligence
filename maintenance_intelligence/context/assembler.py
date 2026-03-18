import datetime as dt
from collections import OrderedDict
from copy import deepcopy
import re
from typing import Dict, Any, List, Optional
import psycopg2
from loguru import logger
from maintenance_intelligence.runner.config import Settings


_CONTEXT_CACHE: "OrderedDict[tuple[Any, ...], Dict[str, Any]]" = OrderedDict()
_CONTEXT_CACHE_STATS: Dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "refreshes": 0,
    "evictions": 0,
    "prefetches": 0,
    "freshness_checks": 0,
    "invalidations": 0,
}

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


def reset_context_cache() -> None:
    _CONTEXT_CACHE.clear()
    for key in _CONTEXT_CACHE_STATS:
        _CONTEXT_CACHE_STATS[key] = 0


def get_context_cache_snapshot() -> Dict[str, int]:
    return {**_CONTEXT_CACHE_STATS, "entries": len(_CONTEXT_CACHE)}


def _isoformat_timestamp(value: Any) -> Optional[str]:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return None


def _empty_context_source_state(asset_id: Optional[str], *, available: bool = False) -> Dict[str, Any]:
    return {
        "asset_id": asset_id,
        "available": available,
        "latest_signal_at": None,
        "latest_rollup_at": None,
        "latest_workorder_at": None,
    }


def _serialize_context_source_state(source_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = source_state or _empty_context_source_state(None)
    return {
        "asset_id": state.get("asset_id"),
        "available": bool(state.get("available", False)),
        "latest_signal_at": _isoformat_timestamp(state.get("latest_signal_at")),
        "latest_rollup_at": _isoformat_timestamp(state.get("latest_rollup_at")),
        "latest_workorder_at": _isoformat_timestamp(state.get("latest_workorder_at")),
    }


def get_context_cache_diagnostics(limit: int = 10) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    ttl_s = int(getattr(Settings(), "context_cache_ttl_s", 60))
    for cache_key, cache_entry in reversed(_CONTEXT_CACHE.items()):
        cached_at = cache_entry.get("cached_at")
        payload = cache_entry.get("payload") or {}
        entries.append(
            {
                "org_id": cache_key[0],
                "site_id": cache_key[1],
                "asset_id": cache_key[2],
                "fleet_wide": bool(cache_key[3]),
                "query": cache_key[4],
                "cached_at": _isoformat_timestamp(cached_at),
                "expires_at": _isoformat_timestamp(
                    cached_at + dt.timedelta(seconds=max(0, ttl_s)) if isinstance(cached_at, dt.datetime) else None
                ),
                "context_scope": payload.get("context_scope"),
                "context_cache": payload.get("context_cache") or {},
                "source_state": _serialize_context_source_state(cache_entry.get("source_state")),
            }
        )
        if len(entries) >= max(1, limit):
            break
    return {
        **get_context_cache_snapshot(),
        "recent_entries": entries,
    }


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


def _normalize_doc_chunks(rows: List[Any], current_asset_id: Optional[str] = None) -> List[Dict[str, Any]]:
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
                "source_scope": "local" if not current_asset_id or row_asset_id == current_asset_id else "fleet",
            }
        )
    return chunks


def _tokenize_fallback_query(query: str) -> List[str]:
    return [token for token in re.sub(r"[^\w\s]", " ", query.lower()).split() if token]


def _score_fallback_doc_chunk(row: Any, query_terms: List[str], current_asset_id: Optional[str] = None) -> tuple[int, int, float, str]:
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


def _rank_fallback_doc_chunks(rows: List[Any], query: str, current_asset_id: Optional[str] = None, limit: int = 3) -> List[Dict[str, Any]]:
    query_terms = _tokenize_fallback_query(query)

    def sort_key(row: Any) -> tuple[int, int, float, str]:
        lexical_score, locality, created_at, chunk_id = _score_fallback_doc_chunk(row, query_terms, current_asset_id)
        return (-lexical_score, locality, -created_at, chunk_id)

    ranked_rows = sorted(
        rows,
        key=sort_key,
    )
    return _normalize_doc_chunks(ranked_rows[:limit], current_asset_id)


def _summarize_fleet_doc_chunks(asset_id: Optional[str], doc_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    external_chunks = [chunk for chunk in doc_chunks if chunk.get("source_scope") == "fleet"]
    referenced_asset_ids = sorted({str(chunk.get("asset_id")) for chunk in external_chunks if chunk.get("asset_id")})
    referenced_sources = sorted({str(chunk.get("source")) for chunk in external_chunks if chunk.get("source")})
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
        part
        for key in sorted(event_details)
        for part in _flatten_detail_value(event_details[key])
    )
    return " ".join(part for part in [event_kind, event_summary, detail_values] if part).strip()


def _context_cache_key(event: Dict[str, Any], fleet_wide: bool) -> tuple[Any, ...]:
    return (
        event.get("org_id"),
        event.get("site_id"),
        event.get("asset_id"),
        fleet_wide,
        _build_rag_query(event),
    )


def _fetch_context_source_state(conn, asset_id: Optional[str]) -> Dict[str, Any]:
    if not asset_id:
        return _empty_context_source_state(asset_id)
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                (SELECT MAX(timestamp) FROM signals WHERE asset_id = %s) AS latest_signal_at,
                (SELECT MAX(end_time) FROM signal_rollups WHERE asset_id = %s) AS latest_rollup_at,
                (
                    SELECT MAX(COALESCE(workorder_created_at, handoff_completed_at, workorder_completed_at, (metadata->>'created_at')::timestamptz))
                    FROM workorders
                    WHERE asset_id = %s
                ) AS latest_workorder_at
            """,
            (asset_id, asset_id, asset_id),
        )
        rows = cur.fetchall()
    row = rows[0] if rows else (None, None, None)
    return {
        "asset_id": asset_id,
        "available": True,
        "latest_signal_at": row[0] if len(row) > 0 else None,
        "latest_rollup_at": row[1] if len(row) > 1 else None,
        "latest_workorder_at": row[2] if len(row) > 2 else None,
    }


def _load_context_source_state(asset_id: Optional[str], settings: Settings, connection_factory=with_pg) -> Dict[str, Any]:
    if not asset_id:
        return _empty_context_source_state(asset_id)
    conn = None
    try:
        conn = connection_factory(settings.pg_dsn)
        return _fetch_context_source_state(conn, asset_id)
    except Exception as exc:
        logger.debug({"event": "ctx.cache.freshness.skip", "err": str(exc), "asset_id": asset_id})
        return _empty_context_source_state(asset_id)
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def _context_source_refresh_reason(previous: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]) -> Optional[str]:
    if not previous or not current:
        return None
    if not previous.get("available") or not current.get("available"):
        return None

    signal_changed = (
        previous.get("latest_signal_at") != current.get("latest_signal_at")
        or previous.get("latest_rollup_at") != current.get("latest_rollup_at")
    )
    workorder_changed = previous.get("latest_workorder_at") != current.get("latest_workorder_at")

    if signal_changed and workorder_changed:
        return "signals-and-workorders-updated"
    if signal_changed:
        return "signals-updated"
    if workorder_changed:
        return "workorders-updated"
    return None


def _context_cache_metadata(
    status: str,
    cached_at: Optional[dt.datetime],
    ttl_s: int,
    *,
    refresh_reason: Optional[str] = None,
    source_state: Optional[Dict[str, Any]] = None,
    freshness_status: str = "unchecked",
) -> Dict[str, Any]:
    expires_at = cached_at + dt.timedelta(seconds=max(0, ttl_s)) if cached_at else None
    return {
        "status": status,
        "cached_at": cached_at.isoformat() if cached_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "ttl_s": ttl_s,
        "refresh_reason": refresh_reason,
        "freshness": {
            "status": freshness_status,
            **_serialize_context_source_state(source_state),
        },
    }


def _cache_hit_payload(
    payload: Dict[str, Any],
    cached_at: dt.datetime,
    ttl_s: int,
    *,
    source_state: Optional[Dict[str, Any]] = None,
    freshness_status: str = "unchecked",
) -> Dict[str, Any]:
    cached_payload = deepcopy(payload)
    cached_payload["context_cache"] = _context_cache_metadata(
        "hit",
        cached_at,
        ttl_s,
        source_state=source_state,
        freshness_status=freshness_status,
    )
    return cached_payload


def _remember_context_payload(
    cache_key: tuple[Any, ...],
    payload: Dict[str, Any],
    ttl_s: int,
    max_entries: int,
    status: str,
    *,
    refresh_reason: Optional[str] = None,
    source_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cached_at = dt.datetime.utcnow()
    stored_payload = deepcopy(payload)
    freshness_status = "current" if source_state and source_state.get("available") else "unchecked"
    stored_payload["context_cache"] = _context_cache_metadata(
        status,
        cached_at,
        ttl_s,
        refresh_reason=refresh_reason,
        source_state=source_state,
        freshness_status=freshness_status,
    )
    _CONTEXT_CACHE[cache_key] = {
        "cached_at": cached_at,
        "payload": deepcopy(stored_payload),
        "source_state": deepcopy(source_state or _empty_context_source_state(cache_key[2])),
    }
    _CONTEXT_CACHE.move_to_end(cache_key)
    while len(_CONTEXT_CACHE) > max(1, max_entries):
        _CONTEXT_CACHE.popitem(last=False)
        _CONTEXT_CACHE_STATS["evictions"] += 1
    return stored_payload


def _get_cached_context(
    cache_key: tuple[Any, ...],
    ttl_s: int,
    settings: Settings,
    connection_factory=with_pg,
) -> tuple[Optional[Dict[str, Any]], Optional[str], Optional[Dict[str, Any]]]:
    cached_entry = _CONTEXT_CACHE.get(cache_key)
    if not cached_entry:
        return None, None, None
    cached_at = cached_entry["cached_at"]
    age_s = (dt.datetime.utcnow() - cached_at).total_seconds()
    if age_s > max(0, ttl_s):
        _CONTEXT_CACHE.pop(cache_key, None)
        _CONTEXT_CACHE_STATS["refreshes"] += 1
        _CONTEXT_CACHE_STATS["invalidations"] += 1
        return None, "ttl-expired", None

    current_source_state = _load_context_source_state(cache_key[2], settings, connection_factory=connection_factory)
    _CONTEXT_CACHE_STATS["freshness_checks"] += 1
    refresh_reason = _context_source_refresh_reason(cached_entry.get("source_state"), current_source_state)
    if refresh_reason is not None:
        _CONTEXT_CACHE.pop(cache_key, None)
        _CONTEXT_CACHE_STATS["refreshes"] += 1
        _CONTEXT_CACHE_STATS["invalidations"] += 1
        return None, refresh_reason, current_source_state

    _CONTEXT_CACHE.move_to_end(cache_key)
    _CONTEXT_CACHE_STATS["hits"] += 1
    freshness_status = "current" if current_source_state.get("available") else "check-failed"
    return (
        _cache_hit_payload(
            cached_entry["payload"],
            cached_at,
            ttl_s,
            source_state=current_source_state,
            freshness_status=freshness_status,
        ),
        None,
        current_source_state,
    )


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


def _fetch_fallback_doc_chunks(conn, asset_id: Optional[str], query: str, fleet_wide: bool = False) -> List[Dict[str, Any]]:
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
            cur.execute(
                """
                SELECT chunk_id, title, content, asset_id, source, created_at FROM doc_chunks
                ORDER BY created_at DESC, chunk_id ASC
                LIMIT 50
                """
            )
        return _rank_fallback_doc_chunks(cur.fetchall(), query, asset_id)


def _fetch_doc_chunks(conn, asset_id: Optional[str], query: str, dsn: str, retriever_cls=None, fleet_wide: bool = False) -> List[Dict[str, Any]]:
    if retriever_cls is None:
        from maintenance_intelligence.rag.retrieval import HybridRetriever

        retriever_cls = HybridRetriever

    try:
        retriever = retriever_cls(dsn)
        chunks = retriever.retrieve(query, asset_id, limit=5, token_budget=2000, fleet_wide=fleet_wide)
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


def _assemble_event_context(event: Dict[str, Any], settings: Settings, connection_factory=with_pg, retriever_cls=None, fleet_wide: Optional[bool] = None) -> Dict[str, Any]:
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
        try:
            out["last_wo_titles"] = _fetch_last_wo_titles(conn, asset_id)
        except Exception as e:
            logger.debug({"event": "ctx.wo.skip", "err": str(e)})

        try:
            out.update(_fetch_signal_context(conn, asset_id))
        except Exception as e:
            logger.debug({"event": "ctx.signals.skip", "err": str(e)})
            out["signal_rollups"] = []
            out["recent_signals"] = []

        try:
            query = _build_rag_query(event)
            out["doc_chunks"] = _fetch_doc_chunks(conn, asset_id, query, settings.pg_dsn, retriever_cls=retriever_cls, fleet_wide=fleet_wide)
            out["fleet_context_summary"] = _summarize_fleet_doc_chunks(asset_id, out["doc_chunks"])
            out["context_scope"] = "local+fleet" if out["fleet_context_summary"]["external_ref_count"] else "local"
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

def get_event_context(event: Dict[str, Any], settings: Optional[Settings] = None, connection_factory=with_pg, retriever_cls=None, fleet_wide: Optional[bool] = None) -> Dict[str, Any]:
    """
    MVP bootstrap context assembly.
    - last_wo_titles: last few WOs for the asset (90d)
    - signal_summary: stub (placeholder)
    - doc_chunks: stub (assumes optional doc_chunks table later)
    Returns empty lists gracefully if tables not present.
    """
    settings = settings or Settings()
    fleet_wide = settings.rca_fleet_wide_context if fleet_wide is None else fleet_wide

    if not settings.context_cache_enabled:
        payload = _assemble_event_context(event, settings, connection_factory=connection_factory, retriever_cls=retriever_cls, fleet_wide=fleet_wide)
        payload["context_cache"] = _context_cache_metadata(
            "disabled",
            None,
            settings.context_cache_ttl_s,
            freshness_status="disabled",
        )
        return payload

    cache_key = _context_cache_key(event, fleet_wide)
    cached_payload, refresh_reason, refreshed_source_state = _get_cached_context(
        cache_key,
        settings.context_cache_ttl_s,
        settings,
        connection_factory=connection_factory,
    )
    if cached_payload is not None:
        return cached_payload

    if refresh_reason is None:
        _CONTEXT_CACHE_STATS["misses"] += 1
    payload = _assemble_event_context(event, settings, connection_factory=connection_factory, retriever_cls=retriever_cls, fleet_wide=fleet_wide)
    source_state = refreshed_source_state or _load_context_source_state(
        event.get("asset_id"),
        settings,
        connection_factory=connection_factory,
    )
    return _remember_context_payload(
        cache_key,
        payload,
        ttl_s=settings.context_cache_ttl_s,
        max_entries=settings.context_cache_max_entries,
        status="refresh" if refresh_reason is not None else "miss",
        refresh_reason=refresh_reason,
        source_state=source_state,
    )


def prefetch_event_contexts(events: List[Dict[str, Any]], settings: Optional[Settings] = None, connection_factory=with_pg, retriever_cls=None, fleet_wide: Optional[bool] = None) -> List[Dict[str, Any]]:
    settings = settings or Settings()
    prefetched: List[Dict[str, Any]] = []
    for event in events:
        prefetched.append(
            get_event_context(
                event,
                settings=settings,
                connection_factory=connection_factory,
                retriever_cls=retriever_cls,
                fleet_wide=fleet_wide,
            )
        )
    if settings.context_cache_enabled:
        _CONTEXT_CACHE_STATS["prefetches"] += len(prefetched)
    return prefetched
