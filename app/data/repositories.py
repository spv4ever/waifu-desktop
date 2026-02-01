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


@dataclass(frozen=True)
class PromptBaseRow:
    key: str
    label: str
    base_prompt: str
    kind: str
    allowed_ratios: list[str]
    iteration_groups: list[str]
    enabled: bool


@dataclass(frozen=True)
class PromptVariationRow:
    group_key: str
    value: str
    position: int
    enabled: bool


@dataclass(frozen=True)
class SocialCopyRow:
    id: int
    text: str
    hashtags: str
    enabled: bool


@dataclass(frozen=True)
class DollimagePromptRow:
    id: int
    group_name: str
    title: str
    prompt_text: str
    typology: str
    enabled: bool


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


class PromptBaseRepository:
    def list(
        self,
        conn: sqlite3.Connection,
        *,
        include_disabled: bool = False,
    ) -> list[PromptBaseRow]:
        rows = conn.execute(
            """
            SELECT key, label, base_prompt, kind, allowed_ratios, iteration_groups, enabled
            FROM prompt_base
            WHERE (? = 1) OR enabled = 1
            ORDER BY kind, label
            """,
            (1 if include_disabled else 0,),
        ).fetchall()

        out: list[PromptBaseRow] = []
        for r in rows:
            allowed_raw = r["allowed_ratios"]
            try:
                allowed_ratios = json.loads(allowed_raw) if allowed_raw else []
            except json.JSONDecodeError:
                allowed_ratios = []
            allowed_ratios = [str(x) for x in allowed_ratios if isinstance(x, (str, int, float))]
            iteration_raw = r["iteration_groups"] if "iteration_groups" in r.keys() else None
            try:
                iteration_groups = json.loads(iteration_raw) if iteration_raw else []
            except json.JSONDecodeError:
                iteration_groups = []
            iteration_groups = [
                str(x) for x in iteration_groups if isinstance(x, (str, int, float)) and str(x).strip()
            ]
            out.append(
                PromptBaseRow(
                    key=str(r["key"]),
                    label=str(r["label"]),
                    base_prompt=str(r["base_prompt"]),
                    kind=str(r["kind"] or "category"),
                    allowed_ratios=allowed_ratios,
                    iteration_groups=iteration_groups,
                    enabled=bool(r["enabled"]),
                )
            )
        return out

    def upsert(
        self,
        conn: sqlite3.Connection,
        *,
        key: str,
        label: str,
        base_prompt: str,
        kind: str = "category",
        allowed_ratios: list[str] | None = None,
        iteration_groups: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        ratios_json = json.dumps(allowed_ratios or [], ensure_ascii=False)
        iteration_json = json.dumps(iteration_groups or [], ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO prompt_base (key, label, base_prompt, kind, allowed_ratios, iteration_groups, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                label = excluded.label,
                base_prompt = excluded.base_prompt,
                kind = excluded.kind,
                allowed_ratios = excluded.allowed_ratios,
                iteration_groups = excluded.iteration_groups,
                enabled = excluded.enabled,
                updated_at = datetime('now')
            """,
            (key, label, base_prompt, kind, ratios_json, iteration_json, 1 if enabled else 0),
        )

    def ensure_seeded(self, conn: sqlite3.Connection, categories: dict[str, Any]) -> int:
        row = conn.execute("SELECT COUNT(*) AS n FROM prompt_base").fetchone()
        if row and int(row["n"]) > 0:
            return 0

        inserted = 0
        for key, data in (categories or {}).items():
            if not isinstance(data, dict):
                continue
            label = str(data.get("label", key))
            base_prompt = str(data.get("base_prompt", "")).strip()
            allowed = data.get("allowed_ratios") or []
            if not isinstance(allowed, list):
                allowed = []
            iteration_groups = data.get("iteration_groups") or []
            if not isinstance(iteration_groups, list):
                iteration_groups = []
            enabled = bool(data.get("enabled", True))
            if not base_prompt:
                continue
            self.upsert(
                conn,
                key=str(key),
                label=label,
                base_prompt=base_prompt,
                kind="category",
                allowed_ratios=[str(x) for x in allowed],
                iteration_groups=[str(x) for x in iteration_groups if str(x).strip()],
                enabled=enabled,
            )
            inserted += 1
        return inserted


class PromptVariationRepository:
    def list(
        self,
        conn: sqlite3.Connection,
        *,
        group_key: str,
        include_disabled: bool = False,
    ) -> list[str]:
        rows = conn.execute(
            """
            SELECT value
            FROM prompt_variation
            WHERE group_key = ?
              AND (? = 1 OR enabled = 1)
            ORDER BY position, id
            """,
            (group_key, 1 if include_disabled else 0),
        ).fetchall()
        return [str(r["value"]) for r in rows]

    def list_rows(
        self,
        conn: sqlite3.Connection,
        *,
        group_key: str,
        include_disabled: bool = False,
    ) -> list[PromptVariationRow]:
        rows = conn.execute(
            """
            SELECT group_key, value, position, enabled
            FROM prompt_variation
            WHERE group_key = ?
              AND (? = 1 OR enabled = 1)
            ORDER BY position, id
            """,
            (group_key, 1 if include_disabled else 0),
        ).fetchall()

        return [
            PromptVariationRow(
                group_key=str(row["group_key"]),
                value=str(row["value"]),
                position=int(row["position"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def list_groups(
        self,
        conn: sqlite3.Connection,
        *,
        include_disabled: bool = False,
    ) -> list[str]:
        rows = conn.execute(
            """
            SELECT DISTINCT group_key
            FROM prompt_variation
            WHERE (? = 1 OR enabled = 1)
            ORDER BY group_key
            """,
            (1 if include_disabled else 0,),
        ).fetchall()
        return [str(row["group_key"]) for row in rows]

    def upsert(
        self,
        conn: sqlite3.Connection,
        *,
        group_key: str,
        value: str,
        position: int,
        enabled: bool = True,
    ) -> None:
        conn.execute(
            """
            INSERT INTO prompt_variation (group_key, value, position, enabled)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(group_key, value) DO UPDATE SET
                position = excluded.position,
                enabled = excluded.enabled,
                updated_at = datetime('now')
            """,
            (group_key, value, position, 1 if enabled else 0),
        )

    def ensure_seeded(self, conn: sqlite3.Connection, groups: dict[str, list[str]]) -> int:
        row = conn.execute("SELECT COUNT(*) AS n FROM prompt_variation").fetchone()
        if row and int(row["n"]) > 0:
            return 0

        inserted = 0
        for group_key, values in (groups or {}).items():
            if not values:
                continue
            for position, value in enumerate(values):
                cleaned = str(value).strip()
                if not cleaned:
                    continue
                self.upsert(
                    conn,
                    group_key=str(group_key),
                    value=cleaned,
                    position=position,
                    enabled=True,
                )
                inserted += 1
        return inserted


class SocialCopyRepository:
    def list(
        self,
        conn: sqlite3.Connection,
        *,
        include_disabled: bool = False,
    ) -> list[SocialCopyRow]:
        rows = conn.execute(
            """
            SELECT id, text, hashtags, enabled
            FROM social_post_copy
            WHERE (? = 1) OR enabled = 1
            ORDER BY id
            """,
            (1 if include_disabled else 0,),
        ).fetchall()

        return [
            SocialCopyRow(
                id=int(row["id"]),
                text=str(row["text"]),
                hashtags=str(row["hashtags"] or ""),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def save(
        self,
        conn: sqlite3.Connection,
        *,
        copy_id: int | None,
        text: str,
        hashtags: str,
        enabled: bool,
    ) -> int:
        if copy_id is None:
            cur = conn.execute(
                """
                INSERT INTO social_post_copy (text, hashtags, enabled)
                VALUES (?, ?, ?)
                """,
                (text, hashtags, 1 if enabled else 0),
            )
            return int(cur.lastrowid)

        conn.execute(
            """
            UPDATE social_post_copy
            SET text = ?, hashtags = ?, enabled = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (text, hashtags, 1 if enabled else 0, copy_id),
        )
        return int(copy_id)

    def delete(self, conn: sqlite3.Connection, *, copy_id: int) -> None:
        conn.execute("DELETE FROM social_post_copy WHERE id = ?", (copy_id,))

    def ensure_seeded(self, conn: sqlite3.Connection, copies: list[dict[str, str]]) -> int:
        row = conn.execute("SELECT COUNT(*) AS n FROM social_post_copy").fetchone()
        if row and int(row["n"]) > 0:
            return 0

        inserted = 0
        for copy in copies or []:
            if not isinstance(copy, dict):
                continue
            text = str(copy.get("text", "")).strip()
            hashtags = str(copy.get("hashtags", "")).strip()
            if not text:
                continue
            conn.execute(
                """
                INSERT INTO social_post_copy (text, hashtags, enabled)
                VALUES (?, ?, 1)
                """,
                (text, hashtags),
            )
            inserted += 1
        return inserted


class DollimagePromptRepository:
    def list(
        self,
        conn: sqlite3.Connection,
        *,
        include_disabled: bool = False,
    ) -> list[DollimagePromptRow]:
        rows = conn.execute(
            """
            SELECT id, group_name, title, prompt_text, typology, enabled
            FROM dollimage_prompt
            WHERE (? = 1) OR enabled = 1
            ORDER BY typology, id
            """,
            (1 if include_disabled else 0,),
        ).fetchall()

        return [
            DollimagePromptRow(
                id=int(row["id"]),
                group_name=str(row["group_name"] or ""),
                title=str(row["title"]),
                prompt_text=str(row["prompt_text"]),
                typology=str(row["typology"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def save(
        self,
        conn: sqlite3.Connection,
        *,
        prompt_id: int | None,
        group_name: str,
        title: str,
        prompt_text: str,
        typology: str,
        enabled: bool,
    ) -> int:
        if prompt_id:
            conn.execute(
                """
                UPDATE dollimage_prompt
                SET group_name = ?, title = ?, prompt_text = ?, typology = ?, enabled = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (group_name, title, prompt_text, typology, 1 if enabled else 0, prompt_id),
            )
            return int(prompt_id)

        cur = conn.execute(
            """
            INSERT INTO dollimage_prompt (group_name, title, prompt_text, typology, enabled)
            VALUES (?, ?, ?, ?, ?)
            """,
            (group_name, title, prompt_text, typology, 1 if enabled else 0),
        )
        return int(cur.lastrowid)

    def delete(self, conn: sqlite3.Connection, *, prompt_id: int) -> None:
        conn.execute("DELETE FROM dollimage_prompt WHERE id = ?", (prompt_id,))


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

    def reset_created_to_queued(self, conn: sqlite3.Connection) -> int:
        cur = conn.execute("UPDATE prompt_item SET status='QUEUED' WHERE status='CREATED'")
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

    def enqueue_missing_for_queued_items(self, conn: sqlite3.Connection, *, priority: int = 100) -> int:
        cur = conn.execute(
            """
            INSERT INTO queue_job(prompt_item_id, priority, status)
            SELECT prompt_item.id, ?, 'PENDING'
            FROM prompt_item
            WHERE prompt_item.status='QUEUED'
              AND NOT EXISTS (
                SELECT 1
                FROM queue_job
                WHERE queue_job.prompt_item_id = prompt_item.id
                  AND queue_job.status IN ('PENDING', 'RUNNING')
              )
            """,
            (priority,),
        )
        return cur.rowcount

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

    def reset_for_retry(self, conn: sqlite3.Connection, job_id: int) -> None:
        conn.execute(
            """
            UPDATE queue_job
            SET status='PENDING',
                remote_id=NULL,
                remote_status=NULL,
                output_json=NULL,
                last_error=NULL,
                progress=0,
                backend_status=NULL
            WHERE id=?
            """,
            (job_id,),
        )

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
