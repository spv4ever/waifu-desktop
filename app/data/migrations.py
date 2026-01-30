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
    _add_column_if_missing(conn, "queue_job", "progress", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "queue_job", "backend_status", "TEXT")

    # prompt_item: outputs finales (base y upscale)
    _add_column_if_missing(conn, "prompt_item", "base_image_json", "TEXT")
    _add_column_if_missing(conn, "prompt_item", "upscale_image_json", "TEXT")
    _add_column_if_missing(conn, "prompt_item", "signature", "TEXT")
    _add_column_if_missing(conn, "prompt_item", "used_in_reel", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(
        conn,
        "prompt_item",
        "updated_at",
        "TEXT",
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
        UPDATE prompt_item
        SET used_in_reel = 0
        WHERE used_in_reel IS NULL
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_prompt_item_inserted_at
        AFTER INSERT ON prompt_item
        FOR EACH ROW
        WHEN NEW.updated_at IS NULL
        BEGIN
          UPDATE prompt_item SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
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

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_base (
          id            INTEGER PRIMARY KEY AUTOINCREMENT,
          key           TEXT NOT NULL UNIQUE,
          label         TEXT NOT NULL,
          base_prompt   TEXT NOT NULL,
          kind          TEXT NOT NULL DEFAULT 'category',
          allowed_ratios TEXT,
          enabled       INTEGER NOT NULL DEFAULT 1,
          created_at    TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_prompt_base_kind_enabled
        ON prompt_base(kind, enabled);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_prompt_base_updated_at
        AFTER UPDATE ON prompt_base
        FOR EACH ROW
        BEGIN
          UPDATE prompt_base SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_variation (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          group_key   TEXT NOT NULL,
          value       TEXT NOT NULL,
          position    INTEGER NOT NULL DEFAULT 0,
          enabled     INTEGER NOT NULL DEFAULT 1,
          created_at  TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE(group_key, value)
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_prompt_variation_group
        ON prompt_variation(group_key, enabled, position);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_prompt_variation_updated_at
        AFTER UPDATE ON prompt_variation
        FOR EACH ROW
        BEGIN
          UPDATE prompt_variation SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS social_post_copy (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          text        TEXT NOT NULL,
          hashtags    TEXT,
          enabled     INTEGER NOT NULL DEFAULT 1,
          created_at  TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_social_post_copy_enabled
        ON social_post_copy(enabled);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_social_post_copy_updated_at
        AFTER UPDATE ON social_post_copy
        FOR EACH ROW
        BEGIN
          UPDATE social_post_copy SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )
