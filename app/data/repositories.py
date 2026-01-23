from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PackRow:
    id: int
    category: str
    variant: str
    requested_n: int


class PackRepository:
    def create(self, conn: sqlite3.Connection, *, category: str, variant: str, requested_n: int, notes: str) -> int:
        cur = conn.execute(
            """
            INSERT INTO prompt_pack(category, variant, requested_n, notes)
            VALUES (?, ?, ?, ?)
            """,
            (category, variant, requested_n, notes),
        )
        return int(cur.lastrowid)


class ComboRegistryRepository:
    def try_register(self, conn: sqlite3.Connection, *, combo_key: str, category: str, variant: str) -> bool:
        """
        Intenta insertar el combo_key. Si ya existe => False (no es único).
        """
        try:
            conn.execute(
                """
                INSERT INTO combo_registry(combo_key, category, variant)
                VALUES (?, ?, ?)
                """,
                (combo_key, category, variant),
            )
            return True
        except sqlite3.IntegrityError:
            return False


class PromptItemRepository:
    def create(
        self,
        conn: sqlite3.Connection,
        *,
        pack_id: int,
        title: str,
        prompt_text: str,
        negative_text: str,
        meta: dict[str, Any],
        signature: str,
        status: str = "CREATED",
    ) -> int:
        """
        signature: firma/hash única.
        Por compatibilidad con schema anterior, también la guardamos en combo_key (NOT NULL).
        """
        meta_json = json.dumps(meta, ensure_ascii=False)
        cur = conn.execute(
            """
            INSERT INTO prompt_item (pack_id, title, prompt_text, negative_text, meta_json, combo_key, signature, status)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (pack_id, title, prompt_text, negative_text, meta_json, signature, signature, status),
        )
        return int(cur.lastrowid)

    def bulk_update_status(self, conn: sqlite3.Connection, *, ids: Iterable[int], status: str) -> None:
        ids = list(ids)
        if not ids:
            return
        placeholders = ",".join(["?"] * len(ids))
        conn.execute(
            f"UPDATE prompt_item SET status = ? WHERE id IN ({placeholders})",
            [status, *ids],
        )

    def get_by_id(self, conn: sqlite3.Connection, item_id: int) -> dict | None:
        row = conn.execute(
            """
            SELECT
                id, title, prompt_text, negative_text, meta_json,
                signature, base_image_json, upscale_image_json, status
            FROM prompt_item
            WHERE id=?
            """,
            (item_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_outputs(
        self,
        conn: sqlite3.Connection,
        *,
        item_id: int,
        base_image_json: str | None,
        upscale_image_json: str | None,
    ) -> None:
        conn.execute(
            """
            UPDATE prompt_item
            SET base_image_json=?, upscale_image_json=?
            WHERE id=?
            """,
            (base_image_json, upscale_image_json, item_id),
        )

    def reset_sent_to_queued(self, conn: sqlite3.Connection) -> int:
        cur = conn.execute("UPDATE prompt_item SET status='QUEUED' WHERE status='SENT'")
        return cur.rowcount


class QueueRepository:
    def enqueue(self, conn: sqlite3.Connection, *, prompt_item_id: int, priority: int = 100) -> int:
        cur = conn.execute(
            """
            INSERT INTO queue_job(prompt_item_id, priority, status)
            VALUES (?, ?, 'PENDING')
            """,
            (prompt_item_id, priority),
        )
        return int(cur.lastrowid)

    def pause_all(self, conn: sqlite3.Connection) -> int:
        cur = conn.execute(
            "UPDATE queue_job SET status = 'CANCELLED' WHERE status IN ('PENDING','RUNNING')"
        )
        return cur.rowcount

    def count_pending(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COUNT(*) AS n FROM queue_job WHERE status='PENDING'").fetchone()
        return int(row["n"]) if row else 0

    def fetch_next_pending(self, conn: sqlite3.Connection) -> dict | None:
        """
        Toma el siguiente job PENDING y lo marca RUNNING de forma segura.
        """
        with conn:
            row = conn.execute(
                """
                SELECT id, prompt_item_id, priority, attempts
                FROM queue_job
                WHERE status='PENDING'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """
            ).fetchone()

            if not row:
                return None

            conn.execute(
                """
                UPDATE queue_job
                SET status='RUNNING', attempts=attempts+1
                WHERE id=? AND status='PENDING'
                """,
                (row["id"],),
            )
            conn.execute(
                """
                UPDATE prompt_item
                SET status='SENT'
                WHERE id=?
                """,
                (row["prompt_item_id"],),
            )

            row2 = conn.execute(
                """
                SELECT id, prompt_item_id, priority, attempts, remote_id, remote_status, progress, backend_status
                FROM queue_job
                WHERE id=?
                """,
                (row["id"],),
            ).fetchone()

            return dict(row2) if row2 else None

    def mark_done(self, conn: sqlite3.Connection, job_id: int) -> None:
        conn.execute("UPDATE queue_job SET status='DONE', last_error=NULL WHERE id=?", (job_id,))

    def mark_failed(self, conn: sqlite3.Connection, job_id: int, error: str) -> None:
        conn.execute("UPDATE queue_job SET status='FAILED', last_error=? WHERE id=?", (error, job_id))

    def reset_running_to_pending(self, conn: sqlite3.Connection) -> int:
        """
        Útil si se cae la app a mitad: vuelve RUNNING -> PENDING.
        """
        cur = conn.execute("UPDATE queue_job SET status='PENDING' WHERE status='RUNNING'")
        return cur.rowcount

    def set_remote(self, conn: sqlite3.Connection, job_id: int, remote_id: str, remote_status: str = "SUBMITTED") -> None:
        conn.execute(
            "UPDATE queue_job SET remote_id=?, remote_status=?, progress=0, backend_status=NULL WHERE id=?",
            (remote_id, remote_status, job_id),
        )

    def set_remote_status(self, conn: sqlite3.Connection, job_id: int, remote_status: str) -> None:
        conn.execute("UPDATE queue_job SET remote_status=? WHERE id=?", (remote_status, job_id))

    def set_progress(self, conn: sqlite3.Connection, job_id: int, progress: int) -> None:
        conn.execute("UPDATE queue_job SET progress=? WHERE id=?", (progress, job_id))

    def set_backend_status(self, conn: sqlite3.Connection, job_id: int, backend_status: str | None) -> None:
        conn.execute("UPDATE queue_job SET backend_status=? WHERE id=?", (backend_status, job_id))

    def set_output_json(self, conn: sqlite3.Connection, job_id: int, output_json: str) -> None:
        conn.execute("UPDATE queue_job SET output_json=? WHERE id=?", (output_json, job_id))

    def get_job(self, conn: sqlite3.Connection, job_id: int) -> dict | None:
        row = conn.execute(
            """
            SELECT id, prompt_item_id, status, attempts, remote_id, remote_status, output_json, progress, backend_status
            FROM queue_job
            WHERE id=?
            """,
            (job_id,),
        ).fetchone()
        return dict(row) if row else None
