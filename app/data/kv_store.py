from __future__ import annotations

import sqlite3


class KVStore:
    def get(self, conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
        row = conn.execute("SELECT v FROM kv_store WHERE k=?", (key,)).fetchone()
        return row["v"] if row else default

    def set(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """
            INSERT INTO kv_store(k, v, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=datetime('now')
            """,
            (key, value),
        )
