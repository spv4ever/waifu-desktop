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
    _add_column_if_missing(
        conn,
        "prompt_item",
        "updated_at",
        "TEXT NOT NULL DEFAULT (datetime('now'))",
    )

    conn.execute(
        """
        UPDATE prompt_item
        SET updated_at = created_at
        WHERE updated_at IS NULL
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_prompt_item_updated_at
        AFTER UPDATE ON prompt_item
        FOR EACH ROW
        BEGIN
          UPDATE prompt_item SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )
