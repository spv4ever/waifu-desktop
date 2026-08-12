from __future__ import annotations

import sqlite3
from pathlib import Path

from app.data.db import SCHEMA_VERSION, _apply_migrations_if_needed


def test_current_version_database_recovers_missing_published_on_x_column() -> None:
    conn = sqlite3.connect(":memory:")
    schema_path = Path(__file__).parents[1] / "app/data/schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.execute("ALTER TABLE prompt_item DROP COLUMN published_on_x")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    _apply_migrations_if_needed(conn)

    columns = {row[1]: row for row in conn.execute("PRAGMA table_info(prompt_item)")}
    assert columns["published_on_x"][4] == "0"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

