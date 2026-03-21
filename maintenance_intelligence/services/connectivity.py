from __future__ import annotations

from typing import Any

import psycopg2


def open_central_connection(pg_dsn: str, *, timeout_s: int = 2):
    timeout = max(1, int(timeout_s))
    return psycopg2.connect(pg_dsn, connect_timeout=timeout)


def safe_close_connection(conn: Any) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass
