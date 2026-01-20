from __future__ import annotations
import sqlite3


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, coldef: str) -> None:
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {r[1] for r in cols}  # r[1] = name
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")


def apply_migrations(conn: sqlite3.Connection) -> None:
    # queue_job: tracking remoto
    _add_column_if_missing(conn, "queue_job", "remote_id", "TEXT")
    _add_column_if_missing(conn, "queue_job", "remote_status", "TEXT")
    _add_column_if_missing(conn, "queue_job", "output_json", "TEXT")

    # prompt_item: outputs finales (base y upscale)
    _add_column_if_missing(conn, "prompt_item", "base_image_json", "TEXT")
    _add_column_if_missing(conn, "prompt_item", "upscale_image_json", "TEXT")
    _add_column_if_missing(conn, "prompt_item", "signature", "TEXT")
