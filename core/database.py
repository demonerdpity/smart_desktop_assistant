from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS clipboard_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    content_hash TEXT UNIQUE,
    created_at TEXT,
    is_pinned INTEGER DEFAULT 0
);
""".strip()


class Database:
    def __init__(self, db_path: Path, *, logger: Optional[logging.Logger] = None) -> None:
        self.db_path = db_path
        self.logger = logger or logging.getLogger(__name__)
        self._local = threading.local()

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(CREATE_TABLE_SQL)
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        self._local.conn = conn
        return conn

    def add_clipboard_text(
        self, content: str, *, max_history: int, content_hash: Optional[str] = None
    ) -> bool:
        if content_hash is None:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        created_at = datetime.now().isoformat(timespec="seconds")
        conn = self._get_conn()
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO clipboard_history (content, content_hash, created_at)
            VALUES (?, ?, ?)
            """,
            (content, content_hash, created_at),
        )
        conn.commit()

        inserted = cur.rowcount == 1
        if inserted:
            self._enforce_history_limit(max_history=max_history)
        return inserted

    def _enforce_history_limit(self, *, max_history: int) -> None:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM clipboard_history").fetchone()[0]
        if total <= max_history:
            return

        to_delete = int(total - max_history)
        cur = conn.execute(
            """
            DELETE FROM clipboard_history
            WHERE id IN (
                SELECT id FROM clipboard_history
                WHERE is_pinned = 0
                ORDER BY id ASC
                LIMIT ?
            )
            """,
            (to_delete,),
        )
        conn.commit()

        if cur.rowcount < to_delete:
            self.logger.warning(
                "History limit exceeded but could not delete enough rows (pinned?). total=%s max=%s",
                total,
                max_history,
            )

    def fetch_clipboard_history(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT id, content, created_at, is_pinned
            FROM clipboard_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

