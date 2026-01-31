from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Iterable
from app.data.db import get_connection
from app.data.kv_store import KVStore
from app.data.repositories import (
    ComboRegistryRepository,
    DollimagePromptRepository,
    DollimagePromptRow,
    PackRepository,
    PromptBaseRepository,
    PromptBaseRow,
    PromptItemRepository,
    SocialCopyRepository,
    SocialCopyRow,
    PromptVariationRow,
    PromptVariationRepository,
    QueueRepository,
)


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


def get_store() -> "BaseStore":
    return SQLiteStore()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_variation_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _extract_variation_groups(catalog: dict[str, Any]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}

    identity = catalog.get("identity", {}) if isinstance(catalog, dict) else {}
    if isinstance(identity, dict):
        groups["identity.face_features"] = _normalize_variation_list(identity.get("face_features"))
        groups["identity.eye_styles"] = _normalize_variation_list(identity.get("eye_styles"))
        hair = identity.get("hair", {})
        if isinstance(hair, dict):
            groups["identity.hair.colors"] = _normalize_variation_list(hair.get("colors"))
            groups["identity.hair.styles"] = _normalize_variation_list(hair.get("styles"))
            groups["identity.hair.details"] = _normalize_variation_list(hair.get("details"))

    camera = catalog.get("camera", {}) if isinstance(catalog, dict) else {}
    if isinstance(camera, dict):
        groups["camera.focal_lengths"] = _normalize_variation_list(camera.get("focal_lengths"))
        groups["camera.framing"] = _normalize_variation_list(camera.get("framing"))
        groups["camera.angle"] = _normalize_variation_list(camera.get("angle"))

    groups["mood"] = _normalize_variation_list(catalog.get("mood")) if isinstance(catalog, dict) else []

    for section in ("combinations", "wardrobe", "footwear", "pose", "background", "lighting"):
        data = catalog.get(section, {}) if isinstance(catalog, dict) else {}
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            groups[f"{section}.{key}"] = _normalize_variation_list(value)

    return {key: value for key, value in groups.items() if value}


def _insert_group_tree(tree: dict[str, Any], parts: list[str], values: list[str]) -> None:
    current = tree
    for part in parts[:-1]:
        if part not in current or not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = list(values)


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

    def list_prompt_variations(self, *, group_key: str, include_disabled: bool = False) -> list[str]:
        raise NotImplementedError

    def list_prompt_variation_rows(
        self,
        *,
        group_key: str,
        include_disabled: bool = False,
    ) -> list[PromptVariationRow]:
        raise NotImplementedError

    def list_prompt_variation_groups(self, *, include_disabled: bool = False) -> list[str]:
        raise NotImplementedError

    def upsert_prompt_variation(
        self,
        *,
        group_key: str,
        value: str,
        position: int,
        enabled: bool = True,
    ) -> None:
        raise NotImplementedError

    def ensure_prompt_variations_seeded(self, catalog: dict[str, Any]) -> int:
        raise NotImplementedError

    def fetch_prompt_variations_tree(self) -> dict[str, Any]:
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

    def list_social_copies(self, *, include_disabled: bool = False) -> list[SocialCopyRow]:
        raise NotImplementedError

    def save_social_copy(
        self,
        *,
        copy_id: int | None,
        text: str,
        hashtags: str,
        enabled: bool,
    ) -> int:
        raise NotImplementedError

    def delete_social_copy(self, *, copy_id: int) -> None:
        raise NotImplementedError

    def ensure_social_copies_seeded(self, copies: list[dict[str, str]]) -> int:
        raise NotImplementedError

    def list_dollimage_prompts(self, *, include_disabled: bool = False) -> list[DollimagePromptRow]:
        raise NotImplementedError

    def save_dollimage_prompt(
        self,
        *,
        prompt_id: int | None,
        group_name: str,
        title: str,
        prompt_text: str,
        typology: str,
        enabled: bool,
    ) -> int:
        raise NotImplementedError

    def delete_dollimage_prompt(self, *, prompt_id: int) -> None:
        raise NotImplementedError


class SQLiteStore(BaseStore):
    def __init__(self) -> None:
        self._packs = PackRepository()
        self._combo = ComboRegistryRepository()
        self._items = PromptItemRepository()
        self._queue = QueueRepository()
        self._prompt_base = PromptBaseRepository()
        self._variations = PromptVariationRepository()
        self._social_copies = SocialCopyRepository()
        self._dollimage_prompts = DollimagePromptRepository()
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
                """
                SELECT title, prompt_text, base_image_json, upscale_image_json, meta_json
                FROM prompt_item
                WHERE id=?
                """,
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

    def list_prompt_variations(self, *, group_key: str, include_disabled: bool = False) -> list[str]:
        with get_connection() as conn:
            return self._variations.list(conn, group_key=group_key, include_disabled=include_disabled)

    def list_prompt_variation_rows(
        self,
        *,
        group_key: str,
        include_disabled: bool = False,
    ) -> list[PromptVariationRow]:
        with get_connection() as conn:
            return self._variations.list_rows(conn, group_key=group_key, include_disabled=include_disabled)

    def list_prompt_variation_groups(self, *, include_disabled: bool = False) -> list[str]:
        with get_connection() as conn:
            return self._variations.list_groups(conn, include_disabled=include_disabled)

    def upsert_prompt_variation(
        self,
        *,
        group_key: str,
        value: str,
        position: int,
        enabled: bool = True,
    ) -> None:
        with get_connection() as conn:
            with conn:
                self._variations.upsert(
                    conn,
                    group_key=group_key,
                    value=value,
                    position=position,
                    enabled=enabled,
                )

    def ensure_prompt_variations_seeded(self, catalog: dict[str, Any]) -> int:
        groups = _extract_variation_groups(catalog)
        if not groups:
            return 0
        with get_connection() as conn:
            with conn:
                return self._variations.ensure_seeded(conn, groups)

    def fetch_prompt_variations_tree(self) -> dict[str, Any]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT group_key, value
                FROM prompt_variation
                WHERE enabled = 1
                ORDER BY group_key, position, id
                """
            ).fetchall()

        grouped: dict[str, list[str]] = {}
        for row in rows:
            group_key = str(row["group_key"])
            grouped.setdefault(group_key, []).append(str(row["value"]))

        tree: dict[str, Any] = {}
        for group_key, values in grouped.items():
            parts = [p for p in group_key.split(".") if p]
            if not parts:
                continue
            _insert_group_tree(tree, parts, values)
        return tree

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

    def list_social_copies(self, *, include_disabled: bool = False) -> list[SocialCopyRow]:
        with get_connection() as conn:
            return self._social_copies.list(conn, include_disabled=include_disabled)

    def save_social_copy(
        self,
        *,
        copy_id: int | None,
        text: str,
        hashtags: str,
        enabled: bool,
    ) -> int:
        with get_connection() as conn:
            return self._social_copies.save(
                conn,
                copy_id=copy_id,
                text=text,
                hashtags=hashtags,
                enabled=enabled,
            )

    def delete_social_copy(self, *, copy_id: int) -> None:
        with get_connection() as conn:
            self._social_copies.delete(conn, copy_id=copy_id)

    def ensure_social_copies_seeded(self, copies: list[dict[str, str]]) -> int:
        with get_connection() as conn:
            with conn:
                return self._social_copies.ensure_seeded(conn, copies)

    def list_dollimage_prompts(self, *, include_disabled: bool = False) -> list[DollimagePromptRow]:
        with get_connection() as conn:
            return self._dollimage_prompts.list(conn, include_disabled=include_disabled)

    def save_dollimage_prompt(
        self,
        *,
        prompt_id: int | None,
        group_name: str,
        title: str,
        prompt_text: str,
        typology: str,
        enabled: bool,
    ) -> int:
        with get_connection() as conn:
            with conn:
                return self._dollimage_prompts.save(
                    conn,
                    prompt_id=prompt_id,
                    group_name=group_name,
                    title=title,
                    prompt_text=prompt_text,
                    typology=typology,
                    enabled=enabled,
                )

    def delete_dollimage_prompt(self, *, prompt_id: int) -> None:
        with get_connection() as conn:
            with conn:
                self._dollimage_prompts.delete(conn, prompt_id=prompt_id)
