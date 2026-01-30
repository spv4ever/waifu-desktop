from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import time
from typing import Any, Iterable

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.config.settings import settings
from app.data.db import get_connection
from app.data.kv_store import KVStore
from app.data.repositories import (
    ComboRegistryRepository,
    PackRepository,
    PromptBaseRepository,
    PromptBaseRow,
    PromptItemRepository,
    QueueRepository,
)


class StorageMode:
    LOCAL = "local"
    MONGO = "mongo"
    DUAL = "dual"


@dataclass(frozen=True)
class QueueJobRow:
    id: int
    prompt_item_id: int
    priority: int
    attempts: int
    remote_id: str | None
    remote_status: str | None
    progress: int | None
    backend_status: str | None


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_mongo_unavailable_until: float = 0.0


def _mark_mongo_unavailable(cooldown_seconds: float = 30.0) -> None:
    global _mongo_unavailable_until
    _mongo_unavailable_until = time.monotonic() + cooldown_seconds


def _mongo_is_available() -> bool:
    return time.monotonic() >= _mongo_unavailable_until


def get_store() -> "BaseStore":
    mode = (settings.data_backend_mode or StorageMode.LOCAL).strip().lower()
    read_pref = (settings.data_backend_read or StorageMode.LOCAL).strip().lower()
    if mode == StorageMode.MONGO:
        if not _mongo_is_available():
            return SQLiteStore()
        try:
            return MongoStore()
        except (RuntimeError, PyMongoError) as exc:
            _mark_mongo_unavailable()
            print(f"[storage] MongoDB no disponible, usando SQLite: {exc}")
            return SQLiteStore()
    if mode == StorageMode.DUAL:
        if not _mongo_is_available():
            return SQLiteStore()
        try:
            return DualStore(read_pref=read_pref)
        except (RuntimeError, PyMongoError) as exc:
            _mark_mongo_unavailable()
            print(f"[storage] MongoDB no disponible, usando SQLite: {exc}")
            return SQLiteStore()
    return SQLiteStore()


class BaseStore:
    def fetch_prompt_filters(self) -> dict[str, list[str]]:
        raise NotImplementedError

    def fetch_prompt_status_counts(self) -> dict[str, int]:
        raise NotImplementedError

    def fetch_queue_status_counts(self) -> dict[str, int]:
        raise NotImplementedError

    def fetch_variants_for_category(self, category: str | None) -> list[str]:
        raise NotImplementedError

    def fetch_category_production_counts(self) -> list[tuple[str, int]]:
        raise NotImplementedError

    def fetch_prompts(
        self,
        *,
        limit: int = 50,
        prompt_id: int | None = None,
        category: str | None = None,
        variant: str | None = None,
        status: str | None = None,
        ratio: str | None = None,
        checkpoint_base: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_prompt_item_media(self, prompt_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_prompt_text(self, prompt_id: int) -> str | None:
        raise NotImplementedError

    def get_prompt_item(self, prompt_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def delete_prompt_item(self, prompt_id: int) -> None:
        raise NotImplementedError

    def get_queue_job_for_prompt(self, prompt_id: int, statuses: Iterable[str]) -> dict[str, Any] | None:
        raise NotImplementedError

    def reset_queue_job_for_retry(self, job_id: int) -> None:
        raise NotImplementedError

    def set_prompt_item_status(self, prompt_id: int, status: str) -> None:
        raise NotImplementedError

    def create_queue_job(self, prompt_item_id: int, priority: int = 100) -> int:
        raise NotImplementedError

    def create_pack(self, *, category: str, variant: str, requested_n: int, notes: str) -> int:
        raise NotImplementedError

    def try_register_combo(self, *, combo_key: str, category: str, variant: str) -> bool:
        raise NotImplementedError

    def create_prompt_item(
        self,
        *,
        pack_id: int,
        title: str,
        prompt_text: str,
        negative_text: str,
        meta: dict[str, Any],
        signature: str,
        status: str,
    ) -> int:
        raise NotImplementedError

    def recover_inflight_jobs(self) -> tuple[int, int, int]:
        raise NotImplementedError

    def fetch_next_pending(self) -> QueueJobRow | None:
        raise NotImplementedError

    def mark_done(self, job_id: int) -> None:
        raise NotImplementedError

    def mark_failed(self, job_id: int, error: str) -> None:
        raise NotImplementedError

    def reset_for_retry(self, job_id: int) -> None:
        raise NotImplementedError

    def set_remote(self, job_id: int, remote_id: str, remote_status: str = "SUBMITTED") -> None:
        raise NotImplementedError

    def set_remote_status(self, job_id: int, remote_status: str) -> None:
        raise NotImplementedError

    def set_progress(self, job_id: int, progress: int) -> None:
        raise NotImplementedError

    def set_backend_status(self, job_id: int, backend_status: str | None) -> None:
        raise NotImplementedError

    def set_output_json(self, job_id: int, output_json: str) -> None:
        raise NotImplementedError

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        raise NotImplementedError

    def set_prompt_outputs(
        self,
        *,
        item_id: int,
        base_image_json: str | None,
        upscale_image_json: str | None,
    ) -> None:
        raise NotImplementedError

    def bulk_update_prompt_status(self, *, ids: Iterable[int], status: str) -> None:
        raise NotImplementedError

    def kv_get(self, key: str, default: str | None = None) -> str | None:
        raise NotImplementedError

    def kv_set(self, key: str, value: str) -> None:
        raise NotImplementedError

    def list_prompt_bases(self, *, include_disabled: bool = False) -> list[PromptBaseRow]:
        raise NotImplementedError

    def upsert_prompt_base(
        self,
        *,
        key: str,
        label: str,
        base_prompt: str,
        kind: str = "category",
        allowed_ratios: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        raise NotImplementedError

    def ensure_prompt_base_seeded(self, categories: dict[str, Any]) -> int:
        raise NotImplementedError

    def select_unused_reel_images(
        self,
        *,
        category: str,
        variant: str | None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def mark_prompt_items_used_in_reel(self, prompt_item_ids: list[int]) -> None:
        raise NotImplementedError


class SQLiteStore(BaseStore):
    def __init__(self) -> None:
        self._packs = PackRepository()
        self._combo = ComboRegistryRepository()
        self._items = PromptItemRepository()
        self._queue = QueueRepository()
        self._prompt_base = PromptBaseRepository()
        self._kv = KVStore()

    def fetch_prompt_filters(self) -> dict[str, list[str]]:
        categories: set[str] = set()
        variants: set[str] = set()
        ratios: set[str] = set()
        statuses: set[str] = set()
        checkpoint_bases: set[str] = set()

        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT status, meta_json
                FROM prompt_item
                ORDER BY id DESC
                """
            ).fetchall()

        for r in rows:
            statuses.add(str(r["status"]))
            meta_json = r["meta_json"]
            if not meta_json:
                continue
            try:
                meta = json.loads(meta_json)
            except json.JSONDecodeError:
                continue
            combo = meta.get("combo", {}) if isinstance(meta, dict) else {}
            category = str(combo.get("category", "?") or "?")
            variant = str(combo.get("variant", "?") or "?")
            ratio = str(
                combo.get("ratio_tag")
                or combo.get("ratio_key")
                or combo.get("ratio")
                or meta.get("ratio")
                or "?"
            )
            checkpoints = meta.get("checkpoints", {}) if isinstance(meta.get("checkpoints"), dict) else {}
            checkpoint_base = checkpoints.get("base")
            if category and category != "?":
                categories.add(category)
            if variant and variant != "?":
                variants.add(variant)
            if ratio and ratio != "?":
                ratios.add(ratio)
            if checkpoint_base:
                checkpoint_bases.add(str(checkpoint_base))

        return {
            "categories": sorted(categories),
            "variants": sorted(variants),
            "ratios": sorted(ratios),
            "statuses": sorted(statuses),
            "checkpoint_bases": sorted(checkpoint_bases),
        }

    def fetch_prompt_status_counts(self) -> dict[str, int]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM prompt_item
                GROUP BY status
                ORDER BY status
                """
            ).fetchall()

        counts = {str(r["status"]): int(r["n"]) for r in rows}
        counts["TOTAL"] = sum(counts.values())
        return counts

    def fetch_queue_status_counts(self) -> dict[str, int]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM queue_job
                GROUP BY status
                ORDER BY status
                """
            ).fetchall()
        return {str(r["status"]): int(r["n"]) for r in rows}

    def fetch_variants_for_category(self, category: str | None) -> list[str]:
        if not category:
            return []
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT json_extract(meta_json, '$.combo.variant') AS variant
                FROM prompt_item
                WHERE status = 'DONE'
                  AND (base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)
                  AND json_extract(meta_json, '$.combo.category') = ?
                ORDER BY variant
                """,
                (category,),
            ).fetchall()

        variants: list[str] = []
        for row in rows:
            value = row["variant"]
            if value is None:
                continue
            variant = str(value).strip()
            if variant and variant != "?":
                variants.append(variant)
        return variants

    def fetch_category_production_counts(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT meta_json
                FROM prompt_item
                WHERE status = 'DONE'
                """
            ).fetchall()

        for r in rows:
            meta_json = r["meta_json"]
            if not meta_json:
                continue
            try:
                meta = json.loads(meta_json)
            except json.JSONDecodeError:
                continue
            combo = meta.get("combo", {}) if isinstance(meta, dict) else {}
            category = str(combo.get("category", "?") or "?")
            if not category or category == "?":
                continue
            counts[category] = counts.get(category, 0) + 1

        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    def fetch_prompts(
        self,
        *,
        limit: int = 50,
        prompt_id: int | None = None,
        category: str | None = None,
        variant: str | None = None,
        status: str | None = None,
        ratio: str | None = None,
        checkpoint_base: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        datestamp_expr = "COALESCE(updated_at, created_at)"

        if category:
            conditions.append("json_extract(meta_json, '$.combo.category') = ?")
            params.append(category)
        if variant:
            conditions.append("json_extract(meta_json, '$.combo.variant') = ?")
            params.append(variant)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if ratio:
            conditions.append(
                "COALESCE(json_extract(meta_json, '$.combo.ratio_tag'),"
                " json_extract(meta_json, '$.combo.ratio_key'),"
                " json_extract(meta_json, '$.combo.ratio'),"
                " json_extract(meta_json, '$.ratio')) = ?"
            )
            params.append(ratio)
        if checkpoint_base:
            conditions.append("json_extract(meta_json, '$.checkpoints.base') = ?")
            params.append(checkpoint_base)
        if prompt_id is not None:
            conditions.append("id = ?")
            params.append(int(prompt_id))
        if date_from:
            conditions.append(f"{datestamp_expr} >= ?")
            params.append(date_from)
        if date_to:
            conditions.append(f"{datestamp_expr} <= ?")
            params.append(date_to)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order_direction = "ASC" if sort_order.lower() == "asc" else "DESC"

        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    title,
                    prompt_text,
                    status,
                    used_in_reel,
                    meta_json,
                    base_image_json,
                    upscale_image_json,
                    (SELECT progress FROM queue_job WHERE prompt_item_id = prompt_item.id ORDER BY id DESC LIMIT 1)
                        AS job_progress,
                    (SELECT backend_status FROM queue_job WHERE prompt_item_id = prompt_item.id ORDER BY id DESC LIMIT 1)
                        AS job_backend_status,
                    (SELECT status FROM queue_job WHERE prompt_item_id = prompt_item.id ORDER BY id DESC LIMIT 1)
                        AS job_status,
                    {datestamp_expr} AS datestamp
                FROM prompt_item
                {where_clause}
                ORDER BY datestamp {order_direction}
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_prompt_item_media(self, prompt_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT title, prompt_text, base_image_json, upscale_image_json FROM prompt_item WHERE id=?",
                (prompt_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_prompt_text(self, prompt_id: int) -> str | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT prompt_text FROM prompt_item WHERE id=?",
                (prompt_id,),
            ).fetchone()
        return str(row["prompt_text"]) if row else None

    def get_prompt_item(self, prompt_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, status, pack_id, title, prompt_text, negative_text, meta_json, combo_key, signature
                FROM prompt_item
                WHERE id=?
                """,
                (prompt_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_prompt_item(self, prompt_id: int) -> None:
        with get_connection() as conn:
            with conn:
                conn.execute("DELETE FROM prompt_item WHERE id=?", (prompt_id,))

    def get_queue_job_for_prompt(self, prompt_id: int, statuses: Iterable[str]) -> dict[str, Any] | None:
        statuses = list(statuses)
        if not statuses:
            return None
        placeholders = ",".join(["?"] * len(statuses))
        with get_connection() as conn:
            row = conn.execute(
                f"""
                SELECT id, status
                FROM queue_job
                WHERE prompt_item_id=? AND status IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (prompt_id, *statuses),
            ).fetchone()
        return dict(row) if row else None

    def reset_queue_job_for_retry(self, job_id: int) -> None:
        with get_connection() as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE queue_job
                    SET status='PENDING',
                        remote_id=NULL,
                        remote_status=NULL,
                        output_json=NULL,
                        last_error=NULL
                    WHERE id=?
                    """,
                    (job_id,),
                )

    def set_prompt_item_status(self, prompt_id: int, status: str) -> None:
        with get_connection() as conn:
            with conn:
                conn.execute("UPDATE prompt_item SET status=? WHERE id=?", (status, prompt_id))

    def create_queue_job(self, prompt_item_id: int, priority: int = 100) -> int:
        with get_connection() as conn:
            with conn:
                return self._queue.enqueue(conn, prompt_item_id=prompt_item_id, priority=priority)

    def _insert_queue_job_with_id(self, *, job_id: int, prompt_item_id: int, priority: int) -> None:
        with get_connection() as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO queue_job(id, prompt_item_id, priority, status, progress, attempts)
                    VALUES (?, ?, ?, 'PENDING', 0, 0)
                    ON CONFLICT(id) DO UPDATE SET
                        prompt_item_id=excluded.prompt_item_id,
                        priority=excluded.priority
                    """,
                    (job_id, prompt_item_id, priority),
                )

    def create_pack(self, *, category: str, variant: str, requested_n: int, notes: str) -> int:
        with get_connection() as conn:
            with conn:
                return self._packs.create(
                    conn,
                    category=category,
                    variant=variant,
                    requested_n=requested_n,
                    notes=notes,
                )

    def _insert_pack_with_id(
        self, *, pack_id: int, category: str, variant: str, requested_n: int, notes: str
    ) -> None:
        with get_connection() as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO prompt_pack(id, category, variant, requested_n, notes)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        category=excluded.category,
                        variant=excluded.variant,
                        requested_n=excluded.requested_n,
                        notes=excluded.notes
                    """,
                    (pack_id, category, variant, requested_n, notes),
                )

    def try_register_combo(self, *, combo_key: str, category: str, variant: str) -> bool:
        with get_connection() as conn:
            with conn:
                return self._combo.try_register(conn, combo_key=combo_key, category=category, variant=variant)

    def create_prompt_item(
        self,
        *,
        pack_id: int,
        title: str,
        prompt_text: str,
        negative_text: str,
        meta: dict[str, Any],
        signature: str,
        status: str,
    ) -> int:
        with get_connection() as conn:
            with conn:
                return self._items.create(
                    conn,
                    pack_id=pack_id,
                    title=title,
                    prompt_text=prompt_text,
                    negative_text=negative_text,
                    meta=meta,
                    signature=signature,
                    status=status,
                )

    def _insert_prompt_item_with_id(
        self,
        *,
        item_id: int,
        pack_id: int,
        title: str,
        prompt_text: str,
        negative_text: str,
        meta: dict[str, Any],
        signature: str,
        status: str,
    ) -> None:
        meta_json = json.dumps(meta, ensure_ascii=False)
        with get_connection() as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO prompt_item (
                        id, pack_id, title, prompt_text, negative_text, meta_json, combo_key, signature, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        pack_id=excluded.pack_id,
                        title=excluded.title,
                        prompt_text=excluded.prompt_text,
                        negative_text=excluded.negative_text,
                        meta_json=excluded.meta_json,
                        combo_key=excluded.combo_key,
                        signature=excluded.signature,
                        status=excluded.status
                    """,
                    (item_id, pack_id, title, prompt_text, negative_text, meta_json, signature, signature, status),
                )

    def recover_inflight_jobs(self) -> tuple[int, int, int]:
        with get_connection() as conn:
            with conn:
                reset_jobs = self._queue.reset_running_to_pending(conn)
                reset_items = self._items.reset_sent_to_queued(conn)
                reset_created = self._items.reset_created_to_queued(conn)
                requeued = self._queue.enqueue_missing_for_queued_items(conn)
        return reset_jobs, reset_items + reset_created, requeued

    def fetch_next_pending(self) -> QueueJobRow | None:
        with get_connection() as conn:
            with conn:
                job = self._queue.fetch_next_pending(conn)
        if not job:
            return None
        return QueueJobRow(
            id=int(job["id"]),
            prompt_item_id=int(job["prompt_item_id"]),
            priority=int(job["priority"]),
            attempts=int(job.get("attempts") or 0),
            remote_id=str(job["remote_id"]) if job.get("remote_id") else None,
            remote_status=str(job["remote_status"]) if job.get("remote_status") else None,
            progress=int(job["progress"]) if isinstance(job.get("progress"), int) else None,
            backend_status=str(job["backend_status"]) if job.get("backend_status") else None,
        )

    def mark_done(self, job_id: int) -> None:
        with get_connection() as conn:
            with conn:
                self._queue.mark_done(conn, job_id)

    def mark_failed(self, job_id: int, error: str) -> None:
        with get_connection() as conn:
            with conn:
                self._queue.mark_failed(conn, job_id, error)

    def reset_for_retry(self, job_id: int) -> None:
        with get_connection() as conn:
            with conn:
                self._queue.reset_for_retry(conn, job_id)

    def set_remote(self, job_id: int, remote_id: str, remote_status: str = "SUBMITTED") -> None:
        with get_connection() as conn:
            with conn:
                self._queue.set_remote(conn, job_id, remote_id, remote_status)

    def set_remote_status(self, job_id: int, remote_status: str) -> None:
        with get_connection() as conn:
            with conn:
                self._queue.set_remote_status(conn, job_id, remote_status)

    def set_progress(self, job_id: int, progress: int) -> None:
        with get_connection() as conn:
            with conn:
                self._queue.set_progress(conn, job_id, progress)

    def set_backend_status(self, job_id: int, backend_status: str | None) -> None:
        with get_connection() as conn:
            with conn:
                self._queue.set_backend_status(conn, job_id, backend_status)

    def set_output_json(self, job_id: int, output_json: str) -> None:
        with get_connection() as conn:
            with conn:
                self._queue.set_output_json(conn, job_id, output_json)

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            return self._queue.get_job(conn, job_id)

    def set_prompt_outputs(
        self,
        *,
        item_id: int,
        base_image_json: str | None,
        upscale_image_json: str | None,
    ) -> None:
        with get_connection() as conn:
            with conn:
                self._items.set_outputs(
                    conn,
                    item_id=item_id,
                    base_image_json=base_image_json,
                    upscale_image_json=upscale_image_json,
                )

    def bulk_update_prompt_status(self, *, ids: Iterable[int], status: str) -> None:
        with get_connection() as conn:
            with conn:
                self._items.bulk_update_status(conn, ids=ids, status=status)

    def kv_get(self, key: str, default: str | None = None) -> str | None:
        with get_connection() as conn:
            return self._kv.get(conn, key, default)

    def kv_set(self, key: str, value: str) -> None:
        with get_connection() as conn:
            with conn:
                self._kv.set(conn, key, value)

    def list_prompt_bases(self, *, include_disabled: bool = False) -> list[PromptBaseRow]:
        with get_connection() as conn:
            return self._prompt_base.list(conn, include_disabled=include_disabled)

    def upsert_prompt_base(
        self,
        *,
        key: str,
        label: str,
        base_prompt: str,
        kind: str = "category",
        allowed_ratios: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        with get_connection() as conn:
            with conn:
                self._prompt_base.upsert(
                    conn,
                    key=key,
                    label=label,
                    base_prompt=base_prompt,
                    kind=kind,
                    allowed_ratios=allowed_ratios,
                    enabled=enabled,
                )

    def ensure_prompt_base_seeded(self, categories: dict[str, Any]) -> int:
        with get_connection() as conn:
            with conn:
                return self._prompt_base.ensure_seeded(conn, categories)

    def select_unused_reel_images(
        self,
        *,
        category: str,
        variant: str | None,
    ) -> list[dict[str, Any]]:
        conditions = [
            "status = 'DONE'",
            "used_in_reel = 0",
            "(base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)",
            "json_extract(meta_json, '$.combo.category') = ?",
        ]
        params: list[str] = [category]
        if variant:
            conditions.append("json_extract(meta_json, '$.combo.variant') = ?")
            params.append(variant)

        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, base_image_json, upscale_image_json
                FROM prompt_item
                WHERE {' AND '.join(conditions)}
                ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                """,
                params,
            ).fetchall()

        return [dict(row) for row in rows]

    def mark_prompt_items_used_in_reel(self, prompt_item_ids: list[int]) -> None:
        if not prompt_item_ids:
            return
        placeholders = ",".join(["?"] * len(prompt_item_ids))
        with get_connection() as conn:
            with conn:
                conn.execute(
                    f"UPDATE prompt_item SET used_in_reel = 1 WHERE id IN ({placeholders})",
                    prompt_item_ids,
                )


class MongoStore(BaseStore):
    def __init__(self) -> None:
        if not settings.mongodb_uri:
            raise RuntimeError("MONGODB_URI no está configurado para usar MongoDB")
        self._client: MongoClient | None = None
        try:
            self._client = MongoClient(
                settings.mongodb_uri,
                serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
                connectTimeoutMS=settings.mongodb_connect_timeout_ms,
                socketTimeoutMS=settings.mongodb_socket_timeout_ms,
            )
            self._client.admin.command("ping")
            self._db = self._client[settings.mongodb_db]
            self._ensure_indexes()
        except PyMongoError as exc:
            if self._client is not None:
                try:
                    self._client.close()
                except PyMongoError:
                    pass
            raise RuntimeError(f"No se pudo conectar a MongoDB: {exc}") from exc

    def _collection(self, name: str):
        return self._db[name]

    def _ensure_indexes(self) -> None:
        self._collection("prompt_item").create_index([("status", 1)])
        self._collection("prompt_item").create_index([("meta.combo.category", 1)])
        self._collection("prompt_item").create_index([("meta.combo.variant", 1)])
        self._collection("prompt_item").create_index([("created_at", -1)])
        self._collection("queue_job").create_index([("status", 1), ("priority", 1), ("created_at", 1)])
        self._collection("queue_job").create_index([("prompt_item_id", 1), ("created_at", -1)])

    def _next_sequence(self, name: str) -> int:
        counters = self._collection("counters")
        max_id = 0
        max_doc = self._collection(name).find_one(sort=[("_id", -1)], projection={"_id": 1})
        if max_doc and max_doc.get("_id") is not None:
            max_id = int(max_doc["_id"])

        doc = counters.find_one({"_id": name}, {"seq": 1})
        if doc is None:
            counters.insert_one({"_id": name, "seq": max_id})
        else:
            current_seq = int(doc.get("seq", 0))
            if current_seq < max_id:
                counters.update_one({"_id": name}, {"$set": {"seq": max_id}})

        doc = counters.find_one_and_update(
            {"_id": name},
            {"$inc": {"seq": 1}},
            return_document=ReturnDocument.AFTER,
        )
        return int(doc["seq"])

    def _serialize_prompt_item(self, doc: dict[str, Any]) -> dict[str, Any]:
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else None
        meta_json = doc.get("meta_json")
        if not meta_json and meta is not None:
            meta_json = json.dumps(meta, ensure_ascii=False)
        return {
            "id": int(doc.get("_id")),
            "status": doc.get("status"),
            "pack_id": doc.get("pack_id"),
            "title": doc.get("title"),
            "prompt_text": doc.get("prompt_text"),
            "negative_text": doc.get("negative_text"),
            "meta_json": meta_json,
            "combo_key": doc.get("combo_key"),
            "signature": doc.get("signature"),
            "used_in_reel": doc.get("used_in_reel"),
            "base_image_json": doc.get("base_image_json"),
            "upscale_image_json": doc.get("upscale_image_json"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }

    def fetch_prompt_filters(self) -> dict[str, list[str]]:
        prompt_items = self._collection("prompt_item")
        statuses = {str(s) for s in prompt_items.distinct("status") if s}
        categories = {str(s) for s in prompt_items.distinct("meta.combo.category") if s and s != "?"}
        variants = {str(s) for s in prompt_items.distinct("meta.combo.variant") if s and s != "?"}
        ratios = {
            *(str(s) for s in prompt_items.distinct("meta.combo.ratio_tag") if s and s != "?"),
            *(str(s) for s in prompt_items.distinct("meta.combo.ratio_key") if s and s != "?"),
            *(str(s) for s in prompt_items.distinct("meta.combo.ratio") if s and s != "?"),
            *(str(s) for s in prompt_items.distinct("meta.ratio") if s and s != "?"),
        }
        checkpoint_bases = {
            str(s) for s in prompt_items.distinct("meta.checkpoints.base") if s and s != "?"
        }
        return {
            "categories": sorted(categories),
            "variants": sorted(variants),
            "ratios": sorted(ratios),
            "statuses": sorted(statuses),
            "checkpoint_bases": sorted(checkpoint_bases),
        }

    def fetch_prompt_status_counts(self) -> dict[str, int]:
        pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        counts = {str(row["_id"]): int(row["n"]) for row in self._collection("prompt_item").aggregate(pipeline)}
        counts["TOTAL"] = sum(counts.values())
        return counts

    def fetch_queue_status_counts(self) -> dict[str, int]:
        pipeline = [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        return {
            str(row["_id"]): int(row["n"]) for row in self._collection("queue_job").aggregate(pipeline)
        }

    def fetch_variants_for_category(self, category: str | None) -> list[str]:
        if not category:
            return []
        values = self._collection("prompt_item").distinct(
            "meta.combo.variant",
            {
                "status": "DONE",
                "meta.combo.category": category,
                "$or": [
                    {"base_image_json": {"$ne": None}},
                    {"upscale_image_json": {"$ne": None}},
                ],
            },
        )
        variants = [str(value).strip() for value in values if value]
        return [variant for variant in variants if variant and variant != "?"]

    def fetch_category_production_counts(self) -> list[tuple[str, int]]:
        pipeline = [
            {"$match": {"status": "DONE"}},
            {"$group": {"_id": "$meta.combo.category", "n": {"$sum": 1}}},
        ]
        rows = list(self._collection("prompt_item").aggregate(pipeline))
        counts = [(str(row["_id"]), int(row["n"])) for row in rows if row.get("_id") not in (None, "?")]
        return sorted(counts, key=lambda item: (-item[1], item[0]))

    def fetch_prompts(
        self,
        *,
        limit: int = 50,
        prompt_id: int | None = None,
        category: str | None = None,
        variant: str | None = None,
        status: str | None = None,
        ratio: str | None = None,
        checkpoint_base: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        match: dict[str, Any] = {}
        if category:
            match["meta.combo.category"] = category
        if variant:
            match["meta.combo.variant"] = variant
        if status:
            match["status"] = status
        if ratio:
            match["$or"] = [
                {"meta.combo.ratio_tag": ratio},
                {"meta.combo.ratio_key": ratio},
                {"meta.combo.ratio": ratio},
                {"meta.ratio": ratio},
            ]
        if checkpoint_base:
            match["meta.checkpoints.base"] = checkpoint_base
        if prompt_id is not None:
            match["_id"] = int(prompt_id)

        pipeline: list[dict[str, Any]] = []
        if match:
            pipeline.append({"$match": match})

        pipeline.append({"$addFields": {"datestamp": {"$ifNull": ["$updated_at", "$created_at"]}}})

        date_match: dict[str, Any] = {}
        if date_from:
            date_match["$gte"] = date_from
        if date_to:
            date_match["$lte"] = date_to
        if date_match:
            pipeline.append({"$match": {"datestamp": date_match}})

        direction = 1 if sort_order.lower() == "asc" else -1
        pipeline.append({"$sort": {"datestamp": direction, "_id": direction}})
        pipeline.append({"$limit": int(limit)})

        docs = list(self._collection("prompt_item").aggregate(pipeline))
        results: list[dict[str, Any]] = []
        queue_jobs = self._collection("queue_job")

        for doc in docs:
            job = queue_jobs.find({"prompt_item_id": doc.get("_id")}).sort(
                [("created_at", -1), ("_id", -1)]
            ).limit(1)
            job_doc = next(job, None)
            results.append(
                {
                    "id": int(doc.get("_id")),
                    "title": doc.get("title"),
                    "prompt_text": doc.get("prompt_text"),
                    "status": doc.get("status"),
                    "used_in_reel": doc.get("used_in_reel"),
                    "meta_json": json.dumps(doc.get("meta") or {}, ensure_ascii=False)
                    if doc.get("meta")
                    else doc.get("meta_json"),
                    "base_image_json": doc.get("base_image_json"),
                    "upscale_image_json": doc.get("upscale_image_json"),
                    "job_progress": job_doc.get("progress") if job_doc else None,
                    "job_backend_status": job_doc.get("backend_status") if job_doc else None,
                    "job_status": job_doc.get("status") if job_doc else None,
                    "datestamp": doc.get("updated_at") or doc.get("created_at"),
                }
            )
        return results

    def get_prompt_item_media(self, prompt_id: int) -> dict[str, Any] | None:
        doc = self._collection("prompt_item").find_one({"_id": int(prompt_id)})
        if not doc:
            return None
        return {
            "title": doc.get("title"),
            "prompt_text": doc.get("prompt_text"),
            "base_image_json": doc.get("base_image_json"),
            "upscale_image_json": doc.get("upscale_image_json"),
        }

    def get_prompt_text(self, prompt_id: int) -> str | None:
        doc = self._collection("prompt_item").find_one({"_id": int(prompt_id)}, {"prompt_text": 1})
        return str(doc.get("prompt_text")) if doc and doc.get("prompt_text") is not None else None

    def get_prompt_item(self, prompt_id: int) -> dict[str, Any] | None:
        doc = self._collection("prompt_item").find_one({"_id": int(prompt_id)})
        return self._serialize_prompt_item(doc) if doc else None

    def delete_prompt_item(self, prompt_id: int) -> None:
        self._collection("prompt_item").delete_one({"_id": int(prompt_id)})
        self._collection("queue_job").delete_many({"prompt_item_id": int(prompt_id)})

    def get_queue_job_for_prompt(self, prompt_id: int, statuses: Iterable[str]) -> dict[str, Any] | None:
        statuses = list(statuses)
        if not statuses:
            return None
        doc = (
            self._collection("queue_job")
            .find({"prompt_item_id": int(prompt_id), "status": {"$in": statuses}})
            .sort([("created_at", -1), ("_id", -1)])
            .limit(1)
        )
        job = next(doc, None)
        if not job:
            return None
        return {"id": int(job.get("_id")), "status": job.get("status")}

    def reset_queue_job_for_retry(self, job_id: int) -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {
                "$set": {
                    "status": "PENDING",
                    "remote_id": None,
                    "remote_status": None,
                    "output_json": None,
                    "last_error": None,
                    "updated_at": _now_str(),
                }
            },
        )

    def set_prompt_item_status(self, prompt_id: int, status: str) -> None:
        self._collection("prompt_item").update_one(
            {"_id": int(prompt_id)},
            {"$set": {"status": status, "updated_at": _now_str()}},
        )

    def create_queue_job(self, prompt_item_id: int, priority: int = 100) -> int:
        job_id = self._next_sequence("queue_job")
        self._collection("queue_job").insert_one(
            {
                "_id": job_id,
                "prompt_item_id": int(prompt_item_id),
                "priority": int(priority),
                "status": "PENDING",
                "progress": 0,
                "attempts": 0,
                "created_at": _now_str(),
                "updated_at": _now_str(),
            }
        )
        return job_id

    def _insert_queue_job_with_id(self, *, job_id: int, prompt_item_id: int, priority: int) -> None:
        self._collection("queue_job").replace_one(
            {"_id": int(job_id)},
            {
                "_id": int(job_id),
                "prompt_item_id": int(prompt_item_id),
                "priority": int(priority),
                "status": "PENDING",
                "progress": 0,
                "attempts": 0,
                "created_at": _now_str(),
                "updated_at": _now_str(),
            },
            upsert=True,
        )

    def create_pack(self, *, category: str, variant: str, requested_n: int, notes: str) -> int:
        pack_id = self._next_sequence("prompt_pack")
        self._collection("prompt_pack").insert_one(
            {
                "_id": pack_id,
                "category": category,
                "variant": variant,
                "requested_n": int(requested_n),
                "notes": notes,
                "created_at": _now_str(),
            }
        )
        return pack_id

    def _insert_pack_with_id(
        self, *, pack_id: int, category: str, variant: str, requested_n: int, notes: str
    ) -> None:
        self._collection("prompt_pack").replace_one(
            {"_id": int(pack_id)},
            {
                "_id": int(pack_id),
                "category": category,
                "variant": variant,
                "requested_n": int(requested_n),
                "notes": notes,
                "created_at": _now_str(),
            },
            upsert=True,
        )

    def try_register_combo(self, *, combo_key: str, category: str, variant: str) -> bool:
        try:
            self._collection("combo_registry").insert_one(
                {
                    "_id": combo_key,
                    "combo_key": combo_key,
                    "category": category,
                    "variant": variant,
                    "created_at": _now_str(),
                }
            )
            return True
        except DuplicateKeyError:
            return False

    def create_prompt_item(
        self,
        *,
        pack_id: int,
        title: str,
        prompt_text: str,
        negative_text: str,
        meta: dict[str, Any],
        signature: str,
        status: str,
    ) -> int:
        item_id = self._next_sequence("prompt_item")
        self._collection("prompt_item").insert_one(
            {
                "_id": item_id,
                "pack_id": int(pack_id),
                "title": title,
                "prompt_text": prompt_text,
                "negative_text": negative_text,
                "meta": meta,
                "meta_json": json.dumps(meta, ensure_ascii=False),
                "combo_key": signature,
                "signature": signature,
                "status": status,
                "used_in_reel": 0,
                "created_at": _now_str(),
                "updated_at": _now_str(),
            }
        )
        return item_id

    def _insert_prompt_item_with_id(
        self,
        *,
        item_id: int,
        pack_id: int,
        title: str,
        prompt_text: str,
        negative_text: str,
        meta: dict[str, Any],
        signature: str,
        status: str,
    ) -> None:
        self._collection("prompt_item").replace_one(
            {"_id": int(item_id)},
            {
                "_id": int(item_id),
                "pack_id": int(pack_id),
                "title": title,
                "prompt_text": prompt_text,
                "negative_text": negative_text,
                "meta": meta,
                "meta_json": json.dumps(meta, ensure_ascii=False),
                "combo_key": signature,
                "signature": signature,
                "status": status,
                "used_in_reel": 0,
                "created_at": _now_str(),
                "updated_at": _now_str(),
            },
            upsert=True,
        )

    def recover_inflight_jobs(self) -> tuple[int, int, int]:
        reset_jobs = self._collection("queue_job").update_many(
            {"status": "RUNNING"},
            {"$set": {"status": "PENDING", "updated_at": _now_str()}},
        ).modified_count
        reset_sent = self._collection("prompt_item").update_many(
            {"status": "SENT"},
            {"$set": {"status": "QUEUED", "updated_at": _now_str()}},
        ).modified_count
        reset_created = self._collection("prompt_item").update_many(
            {"status": "CREATED"},
            {"$set": {"status": "QUEUED", "updated_at": _now_str()}},
        ).modified_count
        existing = set(
            self._collection("queue_job").distinct(
                "prompt_item_id",
                {"status": {"$in": ["PENDING", "RUNNING"]}},
            )
        )
        requeued = 0
        cursor = self._collection("prompt_item").find({"status": "QUEUED"}, {"_id": 1})
        for doc in cursor:
            if doc.get("_id") in existing:
                continue
            self.create_queue_job(prompt_item_id=int(doc.get("_id")))
            requeued += 1
        return int(reset_jobs), int(reset_sent + reset_created), requeued

    def fetch_next_pending(self) -> QueueJobRow | None:
        job = self._collection("queue_job").find_one_and_update(
            {"status": "PENDING"},
            {"$set": {"status": "RUNNING", "updated_at": _now_str()}, "$inc": {"attempts": 1}},
            sort=[("priority", 1), ("created_at", 1), ("_id", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not job:
            return None
        prompt_item_id = int(job.get("prompt_item_id"))
        self._collection("prompt_item").update_one(
            {"_id": prompt_item_id},
            {"$set": {"status": "SENT", "updated_at": _now_str()}},
        )
        return QueueJobRow(
            id=int(job.get("_id")),
            prompt_item_id=prompt_item_id,
            priority=int(job.get("priority") or 0),
            attempts=int(job.get("attempts") or 0),
            remote_id=job.get("remote_id"),
            remote_status=job.get("remote_status"),
            progress=int(job["progress"]) if isinstance(job.get("progress"), int) else None,
            backend_status=job.get("backend_status"),
        )

    def mark_done(self, job_id: int) -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {"$set": {"status": "DONE", "last_error": None, "updated_at": _now_str()}},
        )

    def mark_failed(self, job_id: int, error: str) -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {"$set": {"status": "FAILED", "last_error": error, "updated_at": _now_str()}},
        )

    def reset_for_retry(self, job_id: int) -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {
                "$set": {
                    "status": "PENDING",
                    "remote_id": None,
                    "remote_status": None,
                    "output_json": None,
                    "last_error": None,
                    "progress": 0,
                    "backend_status": None,
                    "updated_at": _now_str(),
                }
            },
        )

    def set_remote(self, job_id: int, remote_id: str, remote_status: str = "SUBMITTED") -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {
                "$set": {
                    "remote_id": remote_id,
                    "remote_status": remote_status,
                    "progress": 0,
                    "backend_status": None,
                    "updated_at": _now_str(),
                }
            },
        )

    def set_remote_status(self, job_id: int, remote_status: str) -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {"$set": {"remote_status": remote_status, "updated_at": _now_str()}},
        )

    def set_progress(self, job_id: int, progress: int) -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {"$set": {"progress": int(progress), "updated_at": _now_str()}},
        )

    def set_backend_status(self, job_id: int, backend_status: str | None) -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {"$set": {"backend_status": backend_status, "updated_at": _now_str()}},
        )

    def set_output_json(self, job_id: int, output_json: str) -> None:
        self._collection("queue_job").update_one(
            {"_id": int(job_id)},
            {"$set": {"output_json": output_json, "updated_at": _now_str()}},
        )

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        doc = self._collection("queue_job").find_one({"_id": int(job_id)})
        return dict(doc) if doc else None

    def set_prompt_outputs(
        self,
        *,
        item_id: int,
        base_image_json: str | None,
        upscale_image_json: str | None,
    ) -> None:
        self._collection("prompt_item").update_one(
            {"_id": int(item_id)},
            {
                "$set": {
                    "base_image_json": base_image_json,
                    "upscale_image_json": upscale_image_json,
                    "updated_at": _now_str(),
                }
            },
        )

    def bulk_update_prompt_status(self, *, ids: Iterable[int], status: str) -> None:
        ids = [int(item_id) for item_id in ids]
        if not ids:
            return
        self._collection("prompt_item").update_many(
            {"_id": {"$in": ids}},
            {"$set": {"status": status, "updated_at": _now_str()}},
        )

    def kv_get(self, key: str, default: str | None = None) -> str | None:
        doc = self._collection("kv_store").find_one({"_id": key})
        if not doc:
            return default
        return doc.get("v", default)

    def kv_set(self, key: str, value: str) -> None:
        self._collection("kv_store").update_one(
            {"_id": key},
            {"$set": {"v": value, "updated_at": _now_str()}},
            upsert=True,
        )

    def list_prompt_bases(self, *, include_disabled: bool = False) -> list[PromptBaseRow]:
        query: dict[str, Any] = {}
        if not include_disabled:
            query["enabled"] = 1
        rows = self._collection("prompt_base").find(query).sort([("kind", 1), ("label", 1)])
        out: list[PromptBaseRow] = []
        for row in rows:
            allowed = row.get("allowed_ratios") or []
            if not isinstance(allowed, list):
                allowed = []
            out.append(
                PromptBaseRow(
                    key=str(row.get("_id")),
                    label=str(row.get("label")),
                    base_prompt=str(row.get("base_prompt")),
                    kind=str(row.get("kind") or "category"),
                    allowed_ratios=[str(x) for x in allowed if isinstance(x, (str, int, float))],
                    enabled=bool(row.get("enabled", True)),
                )
            )
        return out

    def upsert_prompt_base(
        self,
        *,
        key: str,
        label: str,
        base_prompt: str,
        kind: str = "category",
        allowed_ratios: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        self._collection("prompt_base").update_one(
            {"_id": key},
            {
                "$set": {
                    "label": label,
                    "base_prompt": base_prompt,
                    "kind": kind,
                    "allowed_ratios": allowed_ratios or [],
                    "enabled": 1 if enabled else 0,
                    "updated_at": _now_str(),
                },
                "$setOnInsert": {"created_at": _now_str()},
            },
            upsert=True,
        )

    def ensure_prompt_base_seeded(self, categories: dict[str, Any]) -> int:
        existing = self._collection("prompt_base").count_documents({})
        if existing > 0:
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
            enabled = bool(data.get("enabled", True))
            if not base_prompt:
                continue
            self.upsert_prompt_base(
                key=str(key),
                label=label,
                base_prompt=base_prompt,
                kind="category",
                allowed_ratios=[str(x) for x in allowed],
                enabled=enabled,
            )
            inserted += 1
        return inserted

    def select_unused_reel_images(
        self,
        *,
        category: str,
        variant: str | None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "status": "DONE",
            "used_in_reel": 0,
            "$or": [{"base_image_json": {"$ne": None}}, {"upscale_image_json": {"$ne": None}}],
            "meta.combo.category": category,
        }
        if variant:
            query["meta.combo.variant"] = variant
        rows = self._collection("prompt_item").find(query).sort([("updated_at", -1), ("created_at", -1), ("_id", -1)])
        return [self._serialize_prompt_item(row) for row in rows]

    def mark_prompt_items_used_in_reel(self, prompt_item_ids: list[int]) -> None:
        if not prompt_item_ids:
            return
        ids = [int(pid) for pid in prompt_item_ids]
        self._collection("prompt_item").update_many(
            {"_id": {"$in": ids}},
            {"$set": {"used_in_reel": 1, "updated_at": _now_str()}},
        )

    def sync_from_sqlite(self) -> dict[str, int]:
        from app.data.db import get_connection

        counts = {
            "prompt_pack": 0,
            "combo_registry": 0,
            "prompt_item": 0,
            "queue_job": 0,
            "kv_store": 0,
            "prompt_base": 0,
        }
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM prompt_pack").fetchall()
            for row in rows:
                doc = dict(row)
                doc["_id"] = int(doc["id"])
                doc.pop("id", None)
                doc.setdefault("created_at", _now_str())
                self._collection("prompt_pack").replace_one({"_id": doc["_id"]}, doc, upsert=True)
            counts["prompt_pack"] = len(rows)

            rows = conn.execute("SELECT * FROM combo_registry").fetchall()
            for row in rows:
                doc = dict(row)
                doc["_id"] = doc["combo_key"]
                doc.setdefault("created_at", _now_str())
                self._collection("combo_registry").replace_one({"_id": doc["_id"]}, doc, upsert=True)
            counts["combo_registry"] = len(rows)

            rows = conn.execute("SELECT * FROM prompt_item").fetchall()
            for row in rows:
                doc = dict(row)
                meta_json = doc.get("meta_json")
                meta = None
                if meta_json:
                    try:
                        meta = json.loads(meta_json)
                    except json.JSONDecodeError:
                        meta = None
                doc["meta"] = meta or {}
                doc["_id"] = int(doc["id"])
                doc.pop("id", None)
                doc.setdefault("created_at", _now_str())
                doc.setdefault("updated_at", doc.get("created_at"))
                self._collection("prompt_item").replace_one({"_id": doc["_id"]}, doc, upsert=True)
            counts["prompt_item"] = len(rows)

            rows = conn.execute("SELECT * FROM queue_job").fetchall()
            for row in rows:
                doc = dict(row)
                doc["_id"] = int(doc["id"])
                doc.pop("id", None)
                doc.setdefault("created_at", _now_str())
                doc.setdefault("updated_at", doc.get("created_at"))
                self._collection("queue_job").replace_one({"_id": doc["_id"]}, doc, upsert=True)
            counts["queue_job"] = len(rows)

            rows = conn.execute("SELECT * FROM kv_store").fetchall()
            for row in rows:
                doc = dict(row)
                doc["_id"] = doc["k"]
                doc.pop("k", None)
                doc.setdefault("updated_at", _now_str())
                self._collection("kv_store").replace_one({"_id": doc["_id"]}, doc, upsert=True)
            counts["kv_store"] = len(rows)

            rows = conn.execute("SELECT * FROM prompt_base").fetchall()
            for row in rows:
                doc = dict(row)
                doc["_id"] = doc["key"]
                doc.pop("key", None)
                doc.setdefault("created_at", _now_str())
                doc.setdefault("updated_at", doc.get("created_at"))
                allowed = doc.get("allowed_ratios")
                if isinstance(allowed, str):
                    try:
                        doc["allowed_ratios"] = json.loads(allowed) if allowed else []
                    except json.JSONDecodeError:
                        doc["allowed_ratios"] = []
                self._collection("prompt_base").replace_one({"_id": doc["_id"]}, doc, upsert=True)
            counts["prompt_base"] = len(rows)

        return counts


class DualStore(BaseStore):
    def __init__(self, *, read_pref: str) -> None:
        self._primary = SQLiteStore() if read_pref == StorageMode.LOCAL else MongoStore()
        self._secondary = MongoStore() if isinstance(self._primary, SQLiteStore) else SQLiteStore()

    def _read(self) -> BaseStore:
        return self._primary

    def _write(self) -> list[BaseStore]:
        return [self._primary, self._secondary]

    def fetch_prompt_filters(self) -> dict[str, list[str]]:
        return self._read().fetch_prompt_filters()

    def fetch_prompt_status_counts(self) -> dict[str, int]:
        return self._read().fetch_prompt_status_counts()

    def fetch_queue_status_counts(self) -> dict[str, int]:
        return self._read().fetch_queue_status_counts()

    def fetch_variants_for_category(self, category: str | None) -> list[str]:
        return self._read().fetch_variants_for_category(category)

    def fetch_category_production_counts(self) -> list[tuple[str, int]]:
        return self._read().fetch_category_production_counts()

    def fetch_prompts(
        self,
        *,
        limit: int = 50,
        prompt_id: int | None = None,
        category: str | None = None,
        variant: str | None = None,
        status: str | None = None,
        ratio: str | None = None,
        checkpoint_base: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        return self._read().fetch_prompts(
            limit=limit,
            prompt_id=prompt_id,
            category=category,
            variant=variant,
            status=status,
            ratio=ratio,
            checkpoint_base=checkpoint_base,
            date_from=date_from,
            date_to=date_to,
            sort_order=sort_order,
        )

    def get_prompt_item_media(self, prompt_id: int) -> dict[str, Any] | None:
        return self._read().get_prompt_item_media(prompt_id)

    def get_prompt_text(self, prompt_id: int) -> str | None:
        return self._read().get_prompt_text(prompt_id)

    def get_prompt_item(self, prompt_id: int) -> dict[str, Any] | None:
        return self._read().get_prompt_item(prompt_id)

    def delete_prompt_item(self, prompt_id: int) -> None:
        for store in self._write():
            store.delete_prompt_item(prompt_id)

    def get_queue_job_for_prompt(self, prompt_id: int, statuses: Iterable[str]) -> dict[str, Any] | None:
        return self._read().get_queue_job_for_prompt(prompt_id, statuses)

    def reset_queue_job_for_retry(self, job_id: int) -> None:
        for store in self._write():
            store.reset_queue_job_for_retry(job_id)

    def set_prompt_item_status(self, prompt_id: int, status: str) -> None:
        for store in self._write():
            store.set_prompt_item_status(prompt_id, status)

    def create_queue_job(self, prompt_item_id: int, priority: int = 100) -> int:
        job_id = self._primary.create_queue_job(prompt_item_id, priority)
        if self._secondary is not self._primary:
            if hasattr(self._secondary, "_insert_queue_job_with_id"):
                self._secondary._insert_queue_job_with_id(
                    job_id=job_id,
                    prompt_item_id=prompt_item_id,
                    priority=priority,
                )
            else:
                self._secondary.create_queue_job(prompt_item_id, priority)
        return job_id

    def create_pack(self, *, category: str, variant: str, requested_n: int, notes: str) -> int:
        pack_id = self._primary.create_pack(
            category=category,
            variant=variant,
            requested_n=requested_n,
            notes=notes,
        )
        if self._secondary is not self._primary:
            if hasattr(self._secondary, "_insert_pack_with_id"):
                self._secondary._insert_pack_with_id(
                    pack_id=pack_id,
                    category=category,
                    variant=variant,
                    requested_n=requested_n,
                    notes=notes,
                )
            else:
                self._secondary.create_pack(
                    category=category,
                    variant=variant,
                    requested_n=requested_n,
                    notes=notes,
                )
        return pack_id

    def try_register_combo(self, *, combo_key: str, category: str, variant: str) -> bool:
        result = self._primary.try_register_combo(combo_key=combo_key, category=category, variant=variant)
        if self._secondary is not self._primary:
            self._secondary.try_register_combo(combo_key=combo_key, category=category, variant=variant)
        return result

    def create_prompt_item(
        self,
        *,
        pack_id: int,
        title: str,
        prompt_text: str,
        negative_text: str,
        meta: dict[str, Any],
        signature: str,
        status: str,
    ) -> int:
        item_id = self._primary.create_prompt_item(
            pack_id=pack_id,
            title=title,
            prompt_text=prompt_text,
            negative_text=negative_text,
            meta=meta,
            signature=signature,
            status=status,
        )
        if self._secondary is not self._primary:
            if hasattr(self._secondary, "_insert_prompt_item_with_id"):
                self._secondary._insert_prompt_item_with_id(
                    item_id=item_id,
                    pack_id=pack_id,
                    title=title,
                    prompt_text=prompt_text,
                    negative_text=negative_text,
                    meta=meta,
                    signature=signature,
                    status=status,
                )
            else:
                self._secondary.create_prompt_item(
                    pack_id=pack_id,
                    title=title,
                    prompt_text=prompt_text,
                    negative_text=negative_text,
                    meta=meta,
                    signature=signature,
                    status=status,
                )
        return item_id

    def recover_inflight_jobs(self) -> tuple[int, int, int]:
        result = self._primary.recover_inflight_jobs()
        if self._secondary is not self._primary:
            self._secondary.recover_inflight_jobs()
        return result

    def fetch_next_pending(self) -> QueueJobRow | None:
        return self._primary.fetch_next_pending()

    def mark_done(self, job_id: int) -> None:
        for store in self._write():
            store.mark_done(job_id)

    def mark_failed(self, job_id: int, error: str) -> None:
        for store in self._write():
            store.mark_failed(job_id, error)

    def reset_for_retry(self, job_id: int) -> None:
        for store in self._write():
            store.reset_for_retry(job_id)

    def set_remote(self, job_id: int, remote_id: str, remote_status: str = "SUBMITTED") -> None:
        for store in self._write():
            store.set_remote(job_id, remote_id, remote_status)

    def set_remote_status(self, job_id: int, remote_status: str) -> None:
        for store in self._write():
            store.set_remote_status(job_id, remote_status)

    def set_progress(self, job_id: int, progress: int) -> None:
        for store in self._write():
            store.set_progress(job_id, progress)

    def set_backend_status(self, job_id: int, backend_status: str | None) -> None:
        for store in self._write():
            store.set_backend_status(job_id, backend_status)

    def set_output_json(self, job_id: int, output_json: str) -> None:
        for store in self._write():
            store.set_output_json(job_id, output_json)

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        return self._read().get_job(job_id)

    def set_prompt_outputs(
        self,
        *,
        item_id: int,
        base_image_json: str | None,
        upscale_image_json: str | None,
    ) -> None:
        for store in self._write():
            store.set_prompt_outputs(
                item_id=item_id,
                base_image_json=base_image_json,
                upscale_image_json=upscale_image_json,
            )

    def bulk_update_prompt_status(self, *, ids: Iterable[int], status: str) -> None:
        for store in self._write():
            store.bulk_update_prompt_status(ids=ids, status=status)

    def kv_get(self, key: str, default: str | None = None) -> str | None:
        return self._read().kv_get(key, default)

    def kv_set(self, key: str, value: str) -> None:
        for store in self._write():
            store.kv_set(key, value)

    def list_prompt_bases(self, *, include_disabled: bool = False) -> list[PromptBaseRow]:
        return self._read().list_prompt_bases(include_disabled=include_disabled)

    def upsert_prompt_base(
        self,
        *,
        key: str,
        label: str,
        base_prompt: str,
        kind: str = "category",
        allowed_ratios: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        for store in self._write():
            store.upsert_prompt_base(
                key=key,
                label=label,
                base_prompt=base_prompt,
                kind=kind,
                allowed_ratios=allowed_ratios,
                enabled=enabled,
            )

    def ensure_prompt_base_seeded(self, categories: dict[str, Any]) -> int:
        result = self._primary.ensure_prompt_base_seeded(categories)
        if self._secondary is not self._primary:
            self._secondary.ensure_prompt_base_seeded(categories)
        return result

    def select_unused_reel_images(
        self,
        *,
        category: str,
        variant: str | None,
    ) -> list[dict[str, Any]]:
        return self._read().select_unused_reel_images(category=category, variant=variant)

    def mark_prompt_items_used_in_reel(self, prompt_item_ids: list[int]) -> None:
        for store in self._write():
            store.mark_prompt_items_used_in_reel(prompt_item_ids)
