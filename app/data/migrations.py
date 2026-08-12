from __future__ import annotations
import sqlite3


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, coldef: str) -> None:
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {r[1] for r in cols}  # r[1] = name
    if col not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS social_media_post (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          platform TEXT NOT NULL DEFAULT 'x',
          source_url TEXT NOT NULL UNIQUE,
          external_id TEXT,
          title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          author TEXT,
          status TEXT NOT NULL DEFAULT 'DOWNLOADED',
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_social_media_post_created
        ON social_media_post(created_at DESC);

        CREATE TABLE IF NOT EXISTS social_media_asset (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          post_id INTEGER NOT NULL,
          media_type TEXT NOT NULL,
          local_path TEXT NOT NULL UNIQUE,
          original_url TEXT,
          position INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY(post_id) REFERENCES social_media_post(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_social_media_asset_post
        ON social_media_asset(post_id, position);

        CREATE TRIGGER IF NOT EXISTS trg_social_media_post_updated_at
        AFTER UPDATE ON social_media_post
        FOR EACH ROW
        BEGIN
          UPDATE social_media_post SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )
    # queue_job: tracking remoto
    _add_column_if_missing(conn, "queue_job", "remote_id", "TEXT")
    _add_column_if_missing(conn, "queue_job", "remote_status", "TEXT")
    _add_column_if_missing(conn, "queue_job", "output_json", "TEXT")
    _add_column_if_missing(conn, "queue_job", "progress", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "queue_job", "backend_status", "TEXT")
    _add_column_if_missing(conn, "queue_job", "started_at", "TEXT")
    _add_column_if_missing(conn, "queue_job", "completed_at", "TEXT")

    # prompt_item: outputs finales (base y upscale)
    _add_column_if_missing(conn, "prompt_item", "base_image_json", "TEXT")
    _add_column_if_missing(conn, "prompt_item", "upscale_image_json", "TEXT")
    _add_column_if_missing(conn, "prompt_item", "signature", "TEXT")
    _add_column_if_missing(conn, "prompt_item", "used_in_reel", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "prompt_item", "published_on_x", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "prompt_item", "reel_priority", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "prompt_item", "reel_discarded", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(
        conn,
        "prompt_item",
        "updated_at",
        "TEXT",
    )
    _add_column_if_missing(conn, "dollimage_prompt", "group_name", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "prompt_base", "iteration_groups", "TEXT")
    _add_column_if_missing(conn, "anime_character", "description", "TEXT NOT NULL DEFAULT ''")

    conn.execute(
        """
        UPDATE anime_character
        SET description = 'recognizable anime-inspired appearance'
        WHERE description IS NULL OR trim(description) = ''
        """
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
        UPDATE prompt_item
        SET published_on_x = 0
        WHERE published_on_x IS NULL
        """
    )
    conn.execute(
        """
        UPDATE prompt_item
        SET reel_priority = 0
        WHERE reel_priority IS NULL
        """
    )
    conn.execute(
        """
        UPDATE prompt_item
        SET reel_discarded = 0
        WHERE reel_discarded IS NULL
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
          iteration_groups TEXT,
          enabled       INTEGER NOT NULL DEFAULT 1,
          created_at    TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_prompt_item_datestamp
        ON prompt_item(COALESCE(updated_at, created_at));
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_queue_job_prompt_item_latest
        ON queue_job(prompt_item_id, id DESC);
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
        CREATE INDEX IF NOT EXISTS idx_dollimage_prompt_group
        ON dollimage_prompt(group_name, typology, enabled);
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

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dollimage_prompt (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          group_name  TEXT NOT NULL DEFAULT '',
          title       TEXT NOT NULL,
          prompt_text TEXT NOT NULL,
          typology    TEXT NOT NULL,
          enabled     INTEGER NOT NULL DEFAULT 1,
          created_at  TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dollimage_prompt_typology
        ON dollimage_prompt(typology, enabled);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dollimage_prompt_group
        ON dollimage_prompt(group_name, typology, enabled);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_dollimage_prompt_updated_at
        AFTER UPDATE ON dollimage_prompt
        FOR EACH ROW
        BEGIN
          UPDATE dollimage_prompt SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )


    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bulk_image_prompt (
          id              TEXT PRIMARY KEY,
          title           TEXT NOT NULL,
          category        TEXT NOT NULL DEFAULT 'Uncategorized',
          subcategory     TEXT NOT NULL DEFAULT 'General',
          collection      TEXT NOT NULL DEFAULT 'Default',
          subject         TEXT NOT NULL DEFAULT '',
          style           TEXT NOT NULL DEFAULT '',
          mood            TEXT NOT NULL DEFAULT '',
          environment     TEXT NOT NULL DEFAULT '',
          lighting        TEXT NOT NULL DEFAULT '',
          camera          TEXT NOT NULL DEFAULT '',
          composition     TEXT NOT NULL DEFAULT '',
          color_palette   TEXT NOT NULL DEFAULT '',
          ratio           TEXT NOT NULL DEFAULT '',
          model_hint      TEXT NOT NULL DEFAULT '',
          workflow_hint   TEXT NOT NULL DEFAULT '',
          positive_prompt TEXT NOT NULL,
          negative_prompt TEXT NOT NULL DEFAULT '',
          tags_json       TEXT NOT NULL DEFAULT '[]',
          quantity        INTEGER NOT NULL DEFAULT 1,
          priority        INTEGER NOT NULL DEFAULT 100,
          status          TEXT NOT NULL DEFAULT 'draft',
          enabled         INTEGER NOT NULL DEFAULT 1,
          notes           TEXT NOT NULL DEFAULT '',
          created_at      TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bulk_image_prompt_taxonomy
        ON bulk_image_prompt(category, subcategory, priority, title);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_bulk_image_prompt_updated_at
        AFTER UPDATE ON bulk_image_prompt
        FOR EACH ROW
        BEGIN
          UPDATE bulk_image_prompt SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )


    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_prompt_template (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          title       TEXT NOT NULL,
          prompt_text TEXT NOT NULL,
          enabled     INTEGER NOT NULL DEFAULT 1,
          created_at  TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_prompt_template_enabled
        ON video_prompt_template(enabled, title);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_video_prompt_template_updated_at
        AFTER UPDATE ON video_prompt_template
        FOR EACH ROW
        BEGIN
          UPDATE video_prompt_template SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS anime_character (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          list_name   TEXT NOT NULL,
          name        TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          enabled     INTEGER NOT NULL DEFAULT 1,
          created_at  TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE(list_name, name)
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_anime_character_list
        ON anime_character(list_name, enabled, name);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_anime_character_updated_at
        AFTER UPDATE ON anime_character
        FOR EACH ROW
        BEGIN
          UPDATE anime_character SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS anime_prompt (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          title       TEXT NOT NULL,
          prompt_text TEXT NOT NULL,
          enabled     INTEGER NOT NULL DEFAULT 1,
          created_at  TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE(title, prompt_text)
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_anime_prompt_enabled
        ON anime_prompt(enabled, title);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_anime_prompt_updated_at
        AFTER UPDATE ON anime_prompt
        FOR EACH ROW
        BEGIN
          UPDATE anime_prompt SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )
