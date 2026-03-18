from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


class EdgeCommandBuffer:
    def __init__(self, db_path: str):
        self.path = Path(db_path).expanduser()
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
            CREATE TABLE IF NOT EXISTS queued_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id TEXT NOT NULL UNIQUE,
                recommendation_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT
            )
            """
        )
        existing_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(queued_commands)").fetchall()
            if row and row["name"]
        }
        if "replay_attempts" not in existing_columns:
            conn.execute("ALTER TABLE queued_commands ADD COLUMN replay_attempts INTEGER NOT NULL DEFAULT 0")
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

    def _state_value(self, conn: sqlite3.Connection, key: str, default: int = 0) -> int:
        row = conn.execute("SELECT value FROM runtime_state WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return default

    def _increment_state(self, conn: sqlite3.Connection, key: str, amount: int = 1) -> int:
        next_value = self._state_value(conn, key, 0) + int(amount)
        self._set_state(conn, key, next_value)
        return next_value

    def queued_command_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM queued_commands").fetchone()
            return int(row["total"] or 0) if row else 0

    def enqueue_command(self, proposal_id: str, payload: Dict[str, Any], *, error: str | None = None) -> Dict[str, Any]:
        now = _utcnow_iso()
        encoded_payload = json.dumps(payload)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, created_at FROM queued_commands WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE queued_commands SET recommendation_id = ?, payload_json = ?, updated_at = ?, last_error = ? WHERE proposal_id = ?",
                    (
                        _as_text(payload.get("recommendation_id")),
                        encoded_payload,
                        now,
                        error,
                        proposal_id,
                    ),
                )
                queue_id = int(existing["id"])
                created_at = _as_text(existing["created_at"]) or now
            else:
                cursor = conn.execute(
                    "INSERT INTO queued_commands(proposal_id, recommendation_id, payload_json, created_at, updated_at, last_error) VALUES(?, ?, ?, ?, ?, ?)",
                    (
                        proposal_id,
                        _as_text(payload.get("recommendation_id")),
                        encoded_payload,
                        now,
                        now,
                        error,
                    ),
                )
                queue_id = int(cursor.lastrowid or 0)
                created_at = now
                self._increment_state(conn, "total_queued_commands")
            self._set_state(conn, "last_queued_command_at", now)
            conn.commit()
        return {
            "queue_id": queue_id,
            "proposal_id": proposal_id,
            "queued_at": created_at,
            "updated_at": now,
            "last_error": error,
        }

    def get_queued_command(self, proposal_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, proposal_id, recommendation_id, payload_json, created_at, updated_at, last_error, replay_attempts FROM queued_commands WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if not row:
                return {}
            payload = json.loads(row["payload_json"])
            return {
                "queue_id": int(row["id"] or 0),
                "proposal_id": _as_text(row["proposal_id"]),
                "recommendation_id": _as_text(row["recommendation_id"]),
                "payload": payload if isinstance(payload, dict) else {},
                "queued_at": _as_text(row["created_at"]),
                "updated_at": _as_text(row["updated_at"]),
                "last_error": _as_text(row["last_error"]),
                "replay_attempts": int(row["replay_attempts"] or 0),
            }

    def list_queued_commands(self, *, limit: int = 25) -> list[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, proposal_id, recommendation_id, payload_json, created_at, updated_at, last_error, replay_attempts FROM queued_commands ORDER BY id ASC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            commands = []
            for row in rows:
                payload = json.loads(row["payload_json"])
                commands.append(
                    {
                        "queue_id": int(row["id"] or 0),
                        "proposal_id": _as_text(row["proposal_id"]),
                        "recommendation_id": _as_text(row["recommendation_id"]),
                        "payload": payload if isinstance(payload, dict) else {},
                        "queued_at": _as_text(row["created_at"]),
                        "updated_at": _as_text(row["updated_at"]),
                        "last_error": _as_text(row["last_error"]),
                        "replay_attempts": int(row["replay_attempts"] or 0),
                    }
                )
            return commands

    def mark_replay_attempt_started(self) -> None:
        with self._connect() as conn:
            self._set_state(conn, "last_replay_attempt_at", _utcnow_iso())
            conn.commit()

    def record_replay_failure(self, proposal_id: str, error: str) -> None:
        now = _utcnow_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE queued_commands SET replay_attempts = replay_attempts + 1, updated_at = ?, last_error = ? WHERE proposal_id = ?",
                (now, error, proposal_id),
            )
            self._increment_state(conn, "total_replay_failures")
            self._set_state(conn, "last_replay_attempt_at", now)
            self._set_state(conn, "last_error", error)
            conn.commit()

    def record_replay_success(self, proposal_id: str) -> None:
        now = _utcnow_iso()
        with self._connect() as conn:
            conn.execute("DELETE FROM queued_commands WHERE proposal_id = ?", (proposal_id,))
            self._increment_state(conn, "total_replayed_commands")
            self._set_state(conn, "last_replay_attempt_at", now)
            self._set_state(conn, "last_successful_replay_at", now)
            self._set_state(conn, "last_error", None)
            conn.commit()

    def snapshot(self) -> Dict[str, Any]:
        with self._connect() as conn:
            state_rows = conn.execute("SELECT key, value FROM runtime_state").fetchall()
            state = {str(row["key"]): row["value"] for row in state_rows}
            return {
                "queued_command_count": self.queued_command_count(),
                "total_queued_commands": self._state_value(conn, "total_queued_commands", 0),
                "total_replayed_commands": self._state_value(conn, "total_replayed_commands", 0),
                "total_replay_failures": self._state_value(conn, "total_replay_failures", 0),
                "last_queued_command_at": _as_text(state.get("last_queued_command_at")),
                "last_replay_attempt_at": _as_text(state.get("last_replay_attempt_at")),
                "last_successful_replay_at": _as_text(state.get("last_successful_replay_at")),
                "last_error": _as_text(state.get("last_error")),
            }