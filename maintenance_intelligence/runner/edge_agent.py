from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Dict


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EdgeEventBuffer:
    def __init__(self, db_path: str, *, max_events: int = 5000):
        self.path = Path(db_path).expanduser()
        self.max_events = max(1, int(max_events))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._ensure_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS buffered_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                replay_attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()

    def _set_state(self, conn: sqlite3.Connection, key: str, value: Any) -> None:
        encoded = None if value is None else str(value)
        conn.execute(
            "INSERT INTO runtime_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, encoded),
        )

    def _update_state(self, conn: sqlite3.Connection, **fields: Any) -> None:
        self._set_state(conn, "updated_at", _utcnow_iso())
        for key, value in fields.items():
            self._set_state(conn, key, value)

    def buffered_event_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM buffered_events").fetchone()
            return int(row["total"] or 0) if row else 0

    def _prune_if_needed(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT COUNT(*) AS total FROM buffered_events").fetchone()
        total = int(row["total"] or 0) if row else 0
        overflow = total - self.max_events + 1
        if overflow <= 0:
            return
        conn.execute(
            "DELETE FROM buffered_events WHERE id IN (SELECT id FROM buffered_events ORDER BY id ASC LIMIT ?)",
            (overflow,),
        )

    def buffer_event(self, event: Dict[str, Any], *, error: str | None = None) -> int:
        payload_json = json.dumps(event)
        created_at = _utcnow_iso()
        with self._connect() as conn:
            self._prune_if_needed(conn)
            cursor = conn.execute(
                "INSERT INTO buffered_events(event_id, payload_json, created_at, last_error) VALUES(?, ?, ?, ?)",
                (str(event.get("event_id") or ""), payload_json, created_at, error),
            )
            self._update_state(conn, connectivity_status="offline", last_error=error)
            conn.commit()
            return int(cursor.lastrowid or 0)

    def mark_connectivity(self, status: str, *, last_error: str | None = None) -> None:
        with self._connect() as conn:
            self._update_state(conn, connectivity_status=status, last_error=last_error)
            conn.commit()

    def mark_central_write_succeeded(self) -> None:
        now = _utcnow_iso()
        with self._connect() as conn:
            self._update_state(
                conn,
                connectivity_status="online",
                last_successful_central_write_at=now,
                last_error=None,
            )
            conn.commit()

    def replay(self, conn: Any, store_event: Callable[[Any, Dict[str, Any]], None], *, batch_size: int = 100) -> Dict[str, Any]:
        replayed = 0
        last_attempt_at = _utcnow_iso()
        with self._connect() as sqlite_conn:
            rows = sqlite_conn.execute(
                "SELECT id, payload_json FROM buffered_events ORDER BY id ASC LIMIT ?",
                (max(1, int(batch_size)),),
            ).fetchall()
            self._update_state(sqlite_conn, last_replay_attempt_at=last_attempt_at)
            for row in rows:
                payload = json.loads(row["payload_json"])
                try:
                    store_event(conn, payload)
                except Exception as exc:
                    sqlite_conn.execute(
                        "UPDATE buffered_events SET replay_attempts = replay_attempts + 1, last_error = ? WHERE id = ?",
                        (str(exc), row["id"]),
                    )
                    self._update_state(sqlite_conn, connectivity_status="degraded", last_error=str(exc))
                    sqlite_conn.commit()
                    return {
                        "replayed": replayed,
                        "remaining": self.buffered_event_count(),
                        "error": str(exc),
                    }
                sqlite_conn.execute("DELETE FROM buffered_events WHERE id = ?", (row["id"],))
                replayed += 1

            if replayed:
                self._update_state(
                    sqlite_conn,
                    connectivity_status="online",
                    last_successful_central_write_at=_utcnow_iso(),
                    last_error=None,
                )
            sqlite_conn.commit()

        return {
            "replayed": replayed,
            "remaining": self.buffered_event_count(),
            "error": None,
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._connect() as conn:
            state_rows = conn.execute("SELECT key, value FROM runtime_state").fetchall()
            state = {str(row["key"]): row["value"] for row in state_rows}
            return {
                "connectivity_status": state.get("connectivity_status") or "unknown",
                "buffered_event_count": self.buffered_event_count(),
                "last_successful_central_write_at": state.get("last_successful_central_write_at"),
                "last_replay_attempt_at": state.get("last_replay_attempt_at"),
                "last_error": state.get("last_error"),
            }