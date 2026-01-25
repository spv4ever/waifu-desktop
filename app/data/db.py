from __future__ import annotations

from app.data.migrations import apply_migrations
import sqlite3
from pathlib import Path

from app.config.settings import settings


def ensure_data_dir() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    # Importante: FK activas
    conn.execute("PRAGMA foreign_keys = ON;")
    apply_migrations(conn)
    return conn


def init_db(schema_path: Path | None = None) -> None:
    """
    Crea el fichero sqlite y aplica el schema.
    """
    ensure_data_dir()
    schema_path = schema_path or (Path(__file__).with_name("schema.sql"))
    schema_sql = schema_path.read_text(encoding="utf-8")

    with get_connection() as conn:
        conn.executescript(schema_sql)
        conn.commit()
