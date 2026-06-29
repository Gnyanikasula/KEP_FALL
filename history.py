# Chat history - sessions + messages.

import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryStore(ABC):
    """The contract. Reimplement these for MongoDB later."""

    @abstractmethod
    def create_session(self, title: str) -> dict: ...
    @abstractmethod
    def list_sessions(self) -> list[dict]: ...
    @abstractmethod
    def delete_session(self, session_id: str) -> None: ...
    @abstractmethod
    def session_exists(self, session_id: str) -> bool: ...
    @abstractmethod
    def add_message(self, session_id: str, role: str, content: str,
                    verdict: dict | None = None) -> dict: ...
    @abstractmethod
    def get_messages(self, session_id: str) -> list[dict]: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL,
    content TEXT NOT NULL, verdict_json TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    question    TEXT,
    verdict     TEXT,
    rating      INTEGER,
    notes       TEXT,
    ts          TEXT
);
"""


class SQLiteHistoryStore(HistoryStore):
    def __init__(self, db_path: str):
        self.db_path = db_path
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_session(self, title: str = "New session") -> dict:
        sid, created = str(uuid.uuid4()), _now()
        with self._conn() as c:
            c.execute("INSERT INTO sessions (id, title, created_at) VALUES (?,?,?)",
                      (sid, title, created))
        return {"id": sid, "title": title, "created_at": created}

    def list_sessions(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, title, created_at FROM sessions ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def session_exists(self, session_id: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM sessions WHERE id = ?",
                             (session_id,)).fetchone() is not None

    def add_message(self, session_id, role, content, verdict=None) -> dict:
        mid, created = str(uuid.uuid4()), _now()
        vj = json.dumps(verdict) if verdict else None
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages (id, session_id, role, content, verdict_json, created_at) "
                "VALUES (?,?,?,?,?,?)", (mid, session_id, role, content, vj, created))
        return {"id": mid, "session_id": session_id, "role": role,
                "content": content, "verdict": verdict, "created_at": created}

    def get_messages(self, session_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, role, content, verdict_json, created_at "
                "FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["verdict"] = json.loads(d.pop("verdict_json")) if d["verdict_json"] else None
            out.append(d)
        return out

    def add_feedback(self, session_id: str, question: str,
                     verdict: str, rating: int, notes: str = "") -> None:
        """Persist a reviewer's thumbs-up/down rating for a verdict card."""
        with self._conn() as c:
            c.execute(
                "INSERT INTO feedback (session_id, question, verdict, rating, notes, ts) "
                "VALUES (?,?,?,?,?,datetime('now'))",
                (session_id, question, verdict, rating, notes))