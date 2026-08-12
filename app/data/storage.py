from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Iterable
from app.data.db import get_connection
from app.data.kv_store import KVStore
from app.data.repositories import (
    ComboRegistryRepository,
    BulkImagePromptRepository,
    BulkImagePromptRow,
    DollimagePromptRepository,
    DollimagePromptRow,
    PackRepository,
    PromptBaseRepository,
    PromptBaseRow,
    PromptItemRepository,
    SocialCopyRepository,
    SocialCopyRow,
    VideoPromptTemplateRepository,
    VideoPromptTemplateRow,
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


def _extract_variation_groups_for_scope(
    catalog: dict[str, Any],
    *,
    prefix: str | None = None,
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}

    def _add_group(key: str, values: list[str]) -> None:
        full_key = f"{prefix}.{key}" if prefix else key
        groups[full_key] = values

    identity = catalog.get("identity", {}) if isinstance(catalog, dict) else {}
    if isinstance(identity, dict):
        _add_group("identity.face_features", _normalize_variation_list(identity.get("face_features")))
        _add_group("identity.eye_styles", _normalize_variation_list(identity.get("eye_styles")))
        hair = identity.get("hair", {})
        if isinstance(hair, dict):
            _add_group("identity.hair.colors", _normalize_variation_list(hair.get("colors")))
            _add_group("identity.hair.styles", _normalize_variation_list(hair.get("styles")))
            _add_group("identity.hair.details", _normalize_variation_list(hair.get("details")))

    camera = catalog.get("camera", {}) if isinstance(catalog, dict) else {}
    if isinstance(camera, dict):
        _add_group("camera.focal_lengths", _normalize_variation_list(camera.get("focal_lengths")))
        _add_group("camera.framing", _normalize_variation_list(camera.get("framing")))
        _add_group("camera.angle", _normalize_variation_list(camera.get("angle")))

    if isinstance(catalog, dict):
        _add_group("mood", _normalize_variation_list(catalog.get("mood")))

    for section in ("combinations", "wardrobe", "footwear", "pose", "background", "lighting"):
        data = catalog.get(section, {}) if isinstance(catalog, dict) else {}
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            _add_group(f"{section}.{key}", _normalize_variation_list(value))

    return {key: value for key, value in groups.items() if value}


def _extract_variation_groups(catalog: dict[str, Any]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    groups.update(_extract_variation_groups_for_scope(catalog))

    characters = catalog.get("characters", {}) if isinstance(catalog, dict) else {}
    if isinstance(characters, dict):
        for char_key, char_data in characters.items():
            if not isinstance(char_data, dict):
                continue
            prefix = f"characters.{char_key}"
            groups.update(_extract_variation_groups_for_scope(char_data, prefix=prefix))

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

    def fetch_queue_eta_seconds(self) -> int | None:
        raise NotImplementedError

    def fetch_variants_for_category(self, category: str | None) -> list[str]:
        raise NotImplementedError

    def fetch_category_production_counts(self) -> list[tuple[str, int]]:
        raise NotImplementedError

    def list_prompt_images_for_category(self, *, category: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def mark_prompt_items_published_on_x(self, prompt_item_ids: list[int]) -> None:
        raise NotImplementedError

    def clear_prompt_images(self, *, prompt_ids: Iterable[int]) -> int:
        raise NotImplementedError

    def delete_prompt_items(self, *, prompt_ids: Iterable[int]) -> int:
        raise NotImplementedError

    def delete_queued_prompt_items(self) -> int:
        raise NotImplementedError

    def fetch_dollimages_reel_group_counts(self, *, typology: str | None) -> dict[str, int]:
        raise NotImplementedError

    def fetch_dollimages_reel_available_count(
        self,
        *,
        typology: str | None,
        group_name: str | None,
    ) -> int:
        raise NotImplementedError

    def fetch_prompts(
        self,
        *,
        limit: int = 50,
        prompt_id: int | None = None,
        category: str | None = None,
        subcategory: str | None = None,
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

    def update_prompt_item_meta(self, *, prompt_id: int, updates: dict[str, Any]) -> None:
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

    def import_prompt_variations(self, catalog: dict[str, Any], *, replace: bool = False) -> int:
        raise NotImplementedError

    def select_unused_reel_images(
        self,
        *,
        category: str,
        variant: str | None,
        priority_only: bool = False,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def select_unused_dollimages_reel_images(
        self,
        *,
        typology: str | None,
        group_name: str | None,
        priority_only: bool = False,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


    def select_unused_anime_v5_reel_images(
        self,
        *,
        list_name: str | None,
        character: str | None,
        include_nsfw: bool = True,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def mark_prompt_items_used_in_reel(self, prompt_item_ids: list[int]) -> None:
        raise NotImplementedError

    def select_unused_bulk_images_for_youtube_video(self, *, bulk_category: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_bulk_youtube_categories(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def set_prompt_item_reel_flags(
        self,
        *,
        prompt_id: int,
        priority: bool | None = None,
        discarded: bool | None = None,
    ) -> None:
        raise NotImplementedError

    def set_prompt_item_variant(
        self,
        *,
        prompt_id: int,
        variant: str,
        workflow_key: str,
    ) -> None:
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

    def list_bulk_image_prompts(self, *, include_disabled: bool = False) -> list[BulkImagePromptRow]:
        raise NotImplementedError

    def save_bulk_image_prompt(self, prompt: Any) -> int:
        raise NotImplementedError

    def delete_bulk_image_prompt(self, *, prompt_id: str) -> None:
        raise NotImplementedError

    def import_bulk_image_prompts(self, prompts: list[Any]) -> tuple[int, int]:
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

    def import_dollimage_prompts(self, prompts: list[dict[str, Any]], *, replace: bool = False) -> int:
        raise NotImplementedError

    def list_video_prompt_templates(self, *, include_disabled: bool = False) -> list[VideoPromptTemplateRow]:
        raise NotImplementedError

    def save_video_prompt_template(
        self,
        *,
        template_id: int | None,
        title: str,
        prompt_text: str,
        enabled: bool,
    ) -> int:
        raise NotImplementedError

    def delete_video_prompt_template(self, *, template_id: int) -> None:
        raise NotImplementedError

    def ensure_video_prompt_templates_seeded(self, templates: list[dict[str, str]]) -> int:
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
        self._bulk_image_prompts = BulkImagePromptRepository()
        self._dollimage_prompts = DollimagePromptRepository()
        self._video_prompt_templates = VideoPromptTemplateRepository()
        self._kv = KVStore()

    def fetch_prompt_filters(self) -> dict[str, list[str]]:
        categories: set[str] = set()
        subcategories: set[str] = set()
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
            subcategory = str(
                combo.get("subcategory")
                or meta.get("dollimages_prompt_source")
                or meta.get("dollimages_group")
                or "?"
            )
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
            if subcategory and subcategory != "?":
                subcategories.add(subcategory)
            if variant and variant != "?":
                variants.add(variant)
            if ratio and ratio != "?":
                ratios.add(ratio)
            if checkpoint_base:
                checkpoint_bases.add(str(checkpoint_base))

        return {
            "categories": sorted(categories),
            "subcategories": sorted(subcategories),
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

    def fetch_queue_eta_seconds(self) -> int | None:
        with get_connection() as conn:
            active_rows = conn.execute(
                """
                SELECT
                    status,
                    CASE
                        WHEN status = 'RUNNING' AND started_at IS NOT NULL
                        THEN (julianday('now') - julianday(started_at)) * 86400.0
                        ELSE 0
                    END AS elapsed_seconds
                FROM queue_job
                WHERE status IN ('PENDING', 'RUNNING')
                """
            ).fetchall()
            duration_rows = conn.execute(
                """
                SELECT (julianday(completed_at) - julianday(started_at)) * 86400.0 AS seconds
                FROM queue_job
                WHERE status='DONE'
                  AND started_at IS NOT NULL
                  AND completed_at IS NOT NULL
                  AND julianday(completed_at) > julianday(started_at)
                ORDER BY completed_at DESC
                LIMIT 50
                """
            ).fetchall()

        active_jobs = list(active_rows)
        durations = [float(r["seconds"]) for r in duration_rows if r["seconds"] is not None and float(r["seconds"]) > 0]
        if not active_jobs:
            return 0
        if not durations:
            return None

        average_seconds = sum(durations) / len(durations)
        remaining_seconds = 0.0
        for row in active_jobs:
            if row["status"] == "RUNNING":
                elapsed_seconds = float(row["elapsed_seconds"] or 0)
                remaining_seconds += max(average_seconds - elapsed_seconds, 0.0)
            else:
                remaining_seconds += average_seconds
        return int(round(remaining_seconds))

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

    def list_prompt_images_for_category(self, *, category: str) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, base_image_json, upscale_image_json, meta_json, published_on_x
                FROM prompt_item
                WHERE (
                    json_extract(meta_json, '$.combo.category') = ?
                    OR json_extract(meta_json, '$.category') = ?
                    OR json_extract(meta_json, '$.workflow') = ?
                )
                  AND published_on_x = 0
                ORDER BY id
                """,
                (category, category, category),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_prompt_items_published_on_x(self, prompt_item_ids: list[int]) -> None:
        ids = list(dict.fromkeys(int(item_id) for item_id in prompt_item_ids))
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with get_connection() as conn:
            with conn:
                conn.execute(
                    f"UPDATE prompt_item SET published_on_x = 1 WHERE id IN ({placeholders})",
                    ids,
                )

    def clear_prompt_images(self, *, prompt_ids: Iterable[int]) -> int:
        ids = [int(pid) for pid in prompt_ids]
        if not ids:
            return 0
        placeholders = ",".join(["?"] * len(ids))
        with get_connection() as conn:
            with conn:
                cursor = conn.execute(
                    f"""
                    UPDATE prompt_item
                    SET base_image_json=NULL, upscale_image_json=NULL
                    WHERE id IN ({placeholders})
                    """,
                    ids,
                )
        return int(cursor.rowcount or 0)

    def delete_prompt_items(self, *, prompt_ids: Iterable[int]) -> int:
        ids = [int(pid) for pid in prompt_ids]
        if not ids:
            return 0
        placeholders = ",".join(["?"] * len(ids))
        with get_connection() as conn:
            with conn:
                cursor = conn.execute(
                    f"""
                    DELETE FROM prompt_item
                    WHERE id IN ({placeholders})
                    """,
                    ids,
                )
        return int(cursor.rowcount or 0)

    def delete_queued_prompt_items(self) -> int:
        with get_connection() as conn:
            with conn:
                cursor = conn.execute(
                    """
                    DELETE FROM prompt_item
                    WHERE status = 'QUEUED'
                    """
                )
        return int(cursor.rowcount or 0)

    def _dollimages_reel_conditions(
        self,
        *,
        typology: str | None,
        group_name: str | None,
    ) -> tuple[list[str], list[Any]]:
        conditions = [
            "used_in_reel = 0",
            "reel_discarded = 0",
            "(base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)",
            "("
            "json_extract(meta_json, '$.combo.category') = 'dollimages'"
            " OR json_extract(meta_json, '$.workflow') = 'dollimages'"
            " OR json_extract(meta_json, '$.category') = 'dollimages'"
            ")",
        ]
        params: list[Any] = []
        if typology:
            conditions.append(
                "("
                "json_extract(meta_json, '$.combo.variant') = ?"
                " OR json_extract(meta_json, '$.dollimages_typology') = ?"
                ")"
            )
            params.extend([typology, typology])
        if group_name is not None:
            conditions.append("COALESCE(json_extract(meta_json, '$.dollimages_group'), '') = ?")
            params.append(group_name)
        return conditions, params

    def fetch_dollimages_reel_group_counts(self, *, typology: str | None) -> dict[str, int]:
        conditions, params = self._dollimages_reel_conditions(typology=typology, group_name=None)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    COALESCE(json_extract(meta_json, '$.dollimages_group'), '') AS group_name,
                    COUNT(*) AS n
                FROM prompt_item
                WHERE {' AND '.join(conditions)}
                GROUP BY group_name
                ORDER BY group_name
                """,
                params,
            ).fetchall()
        return {str(row["group_name"]): int(row["n"]) for row in rows}

    def fetch_dollimages_reel_available_count(
        self,
        *,
        typology: str | None,
        group_name: str | None,
    ) -> int:
        conditions, params = self._dollimages_reel_conditions(typology=typology, group_name=group_name)
        with get_connection() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM prompt_item
                WHERE {' AND '.join(conditions)}
                """,
                params,
            ).fetchone()
        return int(row["n"]) if row else 0

    def fetch_prompts(
        self,
        *,
        limit: int = 50,
        prompt_id: int | None = None,
        category: str | None = None,
        subcategory: str | None = None,
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
        if subcategory:
            conditions.append(
                "COALESCE(json_extract(meta_json, '$.combo.subcategory'),"
                " json_extract(meta_json, '$.dollimages_prompt_source'),"
                " json_extract(meta_json, '$.dollimages_group')) = ?"
            )
            params.append(subcategory)
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
                WITH latest_prompt_items AS (
                    SELECT
                        id,
                        title,
                        prompt_text,
                        status,
                        used_in_reel,
                        published_on_x,
                        reel_priority,
                        reel_discarded,
                        meta_json,
                        base_image_json,
                        upscale_image_json,
                        {datestamp_expr} AS datestamp
                    FROM prompt_item
                    {where_clause}
                    ORDER BY datestamp {order_direction}
                    LIMIT ?
                ),
                latest_queue_job AS (
                    SELECT q.prompt_item_id, q.progress, q.backend_status, q.status
                    FROM queue_job q
                    INNER JOIN (
                        SELECT prompt_item_id, MAX(id) AS id
                        FROM queue_job
                        WHERE prompt_item_id IN (SELECT id FROM latest_prompt_items)
                        GROUP BY prompt_item_id
                    ) latest ON latest.id = q.id
                )
                SELECT
                    p.id,
                    p.title,
                    p.prompt_text,
                    p.status,
                    p.used_in_reel,
                    p.published_on_x,
                    p.reel_priority,
                    p.reel_discarded,
                    p.meta_json,
                    p.base_image_json,
                    p.upscale_image_json,
                    q.progress AS job_progress,
                    q.backend_status AS job_backend_status,
                    q.status AS job_status,
                    p.datestamp AS datestamp
                FROM latest_prompt_items p
                LEFT JOIN latest_queue_job q ON q.prompt_item_id = p.id
                ORDER BY p.datestamp {order_direction}
                """,
                (*params, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def select_unused_dollimages_reel_images(
        self,
        *,
        typology: str | None,
        group_name: str | None,
        priority_only: bool = False,
    ) -> list[dict[str, Any]]:
        conditions, params = self._dollimages_reel_conditions(
            typology=typology,
            group_name=group_name,
        )
        if priority_only:
            conditions.append("reel_priority = 1")

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

    def get_prompt_item_media(self, prompt_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    p.title,
                    p.prompt_text,
                    p.base_image_json,
                    p.upscale_image_json,
                    p.meta_json,
                    (
                        SELECT q.output_json
                        FROM queue_job q
                        WHERE q.prompt_item_id = p.id AND q.output_json IS NOT NULL
                        ORDER BY q.id DESC
                        LIMIT 1
                    ) AS output_json
                FROM prompt_item p
                WHERE p.id=?
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

    def update_prompt_item_meta(self, *, prompt_id: int, updates: dict[str, Any]) -> None:
        if not updates:
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT meta_json FROM prompt_item WHERE id = ?",
                (prompt_id,),
            ).fetchone()
            if not row:
                return
            meta_json = row["meta_json"]
            if meta_json:
                try:
                    parsed = json.loads(meta_json)
                    meta = parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    meta = {}
            else:
                meta = {}
            meta.update(updates)
            updated_meta = json.dumps(meta, ensure_ascii=False)
            conn.execute(
                "UPDATE prompt_item SET meta_json = ? WHERE id = ?",
                (updated_meta, prompt_id),
            )

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
                        last_error=NULL,
                        progress=0,
                        backend_status=NULL,
                        started_at=NULL,
                        completed_at=NULL
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
        iteration_groups: list[str] | None = None,
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
                    iteration_groups=iteration_groups,
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

    def import_prompt_variations(self, catalog: dict[str, Any], *, replace: bool = False) -> int:
        groups = _extract_variation_groups(catalog)
        if not groups:
            return 0
        inserted = 0
        with get_connection() as conn:
            with conn:
                if replace:
                    conn.execute("DELETE FROM prompt_variation")
                for group_key, values in groups.items():
                    if not values:
                        continue
                    for position, value in enumerate(values):
                        cleaned = str(value).strip()
                        if not cleaned:
                            continue
                        self._variations.upsert(
                            conn,
                            group_key=str(group_key),
                            value=cleaned,
                            position=position,
                            enabled=True,
                        )
                        inserted += 1
        return inserted

    def select_unused_reel_images(
        self,
        *,
        category: str,
        variant: str | None,
        priority_only: bool = False,
    ) -> list[dict[str, Any]]:
        conditions = [
            "status = 'DONE'",
            "used_in_reel = 0",
            "reel_discarded = 0",
            "(base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)",
            "json_extract(meta_json, '$.combo.category') = ?",
        ]
        params: list[str] = [category]
        if priority_only:
            conditions.append("reel_priority = 1")
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


    def select_unused_anime_v5_reel_images(
        self,
        *,
        list_name: str | None,
        character: str | None,
        include_nsfw: bool = True,
    ) -> list[dict[str, Any]]:
        conditions = [
            "status = 'DONE'",
            "used_in_reel = 0",
            "reel_discarded = 0",
            "(base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)",
            "json_extract(meta_json, '$.workflow') = 'anime_v5'",
        ]
        params: list[str] = []
        if list_name:
            conditions.append("json_extract(meta_json, '$.anime_character_list') = ?")
            params.append(list_name)
        if character:
            conditions.append("json_extract(meta_json, '$.anime_character') = ?")
            params.append(character)
        if not include_nsfw:
            conditions.append("COALESCE(json_extract(meta_json, '$.anime_v5_content_rating'), 'sfw') != 'nsfw'")

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

    def select_unused_bulk_images_for_youtube_video(self, *, bulk_category: str) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, base_image_json, upscale_image_json
                FROM prompt_item
                WHERE status = 'DONE'
                  AND used_in_reel = 0
                  AND reel_discarded = 0
                  AND (base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)
                  AND json_extract(meta_json, '$.source') = 'bulk_images'
                  AND json_extract(meta_json, '$.bulk_metadata.category') = ?
                ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                """,
                (bulk_category,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_bulk_youtube_categories(self) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT json_extract(meta_json, '$.bulk_metadata.category') AS category, COUNT(*) AS available_count
                FROM prompt_item
                WHERE status = 'DONE'
                  AND used_in_reel = 0
                  AND reel_discarded = 0
                  AND (base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)
                  AND json_extract(meta_json, '$.source') = 'bulk_images'
                  AND COALESCE(json_extract(meta_json, '$.bulk_metadata.category'), '') <> ''
                GROUP BY category
                ORDER BY category COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def set_prompt_item_reel_flags(
        self,
        *,
        prompt_id: int,
        priority: bool | None = None,
        discarded: bool | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[object] = []
        if priority is not None:
            updates.append("reel_priority = ?")
            params.append(1 if priority else 0)
        if discarded is not None:
            updates.append("reel_discarded = ?")
            params.append(1 if discarded else 0)
        if not updates:
            return
        params.append(int(prompt_id))
        with get_connection() as conn:
            with conn:
                conn.execute(
                    f"UPDATE prompt_item SET {', '.join(updates)} WHERE id = ?",
                    params,
                )

    def set_prompt_item_variant(
        self,
        *,
        prompt_id: int,
        variant: str,
        workflow_key: str,
    ) -> None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT meta_json FROM prompt_item WHERE id = ?",
                (prompt_id,),
            ).fetchone()
        if not row:
            return
        meta_json = row["meta_json"]
        meta: dict[str, Any]
        if meta_json:
            try:
                parsed = json.loads(meta_json)
                meta = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                meta = {}
        else:
            meta = {}

        combo = meta.get("combo")
        if not isinstance(combo, dict):
            combo = {}
        combo["variant"] = variant
        meta["combo"] = combo
        if workflow_key == "dollimages":
            meta["dollimages_typology"] = variant

        updated_meta = json.dumps(meta, ensure_ascii=False)
        with get_connection() as conn:
            with conn:
                conn.execute(
                    "UPDATE prompt_item SET meta_json = ? WHERE id = ?",
                    (updated_meta, prompt_id),
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

    def list_bulk_image_prompts(self, *, include_disabled: bool = False) -> list[BulkImagePromptRow]:
        with get_connection() as conn:
            return self._bulk_image_prompts.list(conn, include_disabled=include_disabled)

    def save_bulk_image_prompt(self, prompt: Any) -> int:
        with get_connection() as conn:
            with conn:
                existed = conn.execute(
                    "SELECT 1 FROM bulk_image_prompt WHERE id = ? LIMIT 1",
                    (prompt.id,),
                ).fetchone()
                self._bulk_image_prompts.save(conn, prompt)
                return 0 if existed else 1

    def delete_bulk_image_prompt(self, *, prompt_id: str) -> None:
        with get_connection() as conn:
            with conn:
                self._bulk_image_prompts.delete(conn, prompt_id=prompt_id)

    def import_bulk_image_prompts(self, prompts: list[Any]) -> tuple[int, int]:
        if not prompts:
            return 0, 0
        added = 0
        updated = 0
        with get_connection() as conn:
            with conn:
                existing = {str(row["id"]) for row in conn.execute("SELECT id FROM bulk_image_prompt").fetchall()}
                for prompt in prompts:
                    self._bulk_image_prompts.save(conn, prompt)
                    if prompt.id in existing:
                        updated += 1
                    else:
                        added += 1
                        existing.add(prompt.id)
        return added, updated

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

    def import_dollimage_prompts(self, prompts: list[dict[str, Any]], *, replace: bool = False) -> int:
        if not prompts:
            return 0
        inserted = 0
        with get_connection() as conn:
            with conn:
                if replace:
                    conn.execute("DELETE FROM dollimage_prompt")
                for prompt in prompts:
                    group_name = str(prompt.get("group_name", "") or "")
                    title = str(prompt.get("title", "") or "")
                    prompt_text = str(prompt.get("prompt_text", "") or "")
                    typology = str(prompt.get("typology", "normal") or "normal")
                    enabled = bool(prompt.get("enabled", True))
                    if not title or not prompt_text:
                        continue
                    self._dollimage_prompts.save(
                        conn,
                        prompt_id=None,
                        group_name=group_name,
                        title=title,
                        prompt_text=prompt_text,
                        typology=typology,
                        enabled=enabled,
                    )
                    inserted += 1
        return inserted

    def list_video_prompt_templates(self, *, include_disabled: bool = False) -> list[VideoPromptTemplateRow]:
        with get_connection() as conn:
            return self._video_prompt_templates.list(conn, include_disabled=include_disabled)

    def save_video_prompt_template(
        self,
        *,
        template_id: int | None,
        title: str,
        prompt_text: str,
        enabled: bool,
    ) -> int:
        with get_connection() as conn:
            with conn:
                return self._video_prompt_templates.save(
                    conn,
                    template_id=template_id,
                    title=title,
                    prompt_text=prompt_text,
                    enabled=enabled,
                )

    def delete_video_prompt_template(self, *, template_id: int) -> None:
        with get_connection() as conn:
            with conn:
                self._video_prompt_templates.delete(conn, template_id=template_id)

    def ensure_video_prompt_templates_seeded(self, templates: list[dict[str, str]]) -> int:
        with get_connection() as conn:
            with conn:
                return self._video_prompt_templates.ensure_seeded(conn, templates)

    def list_anime_character_lists(self, *, include_disabled: bool = False, include_descriptions: bool = False) -> dict[str, list[str]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT list_name, name, description
                FROM anime_character
                WHERE (? = 1) OR enabled = 1
                ORDER BY list_name, name
                """,
                (1 if include_disabled else 0,),
            ).fetchall()
        out: dict[str, list[str]] = {}
        for row in rows:
            description = str(row["description"] or "").strip()
            if include_descriptions and description:
                value = json.dumps(
                    {"name": str(row["name"]), "anime": str(row["list_name"]), "description": description},
                    ensure_ascii=False,
                )
            else:
                value = str(row["name"])
            out.setdefault(str(row["list_name"]), []).append(value)
        return out

    def list_anime_prompts(self, *, include_disabled: bool = False) -> list[dict[str, object]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, prompt_text, enabled
                FROM anime_prompt
                WHERE (? = 1) OR enabled = 1
                ORDER BY title, id
                """,
                (1 if include_disabled else 0,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "title": str(row["title"]),
                "prompt_text": str(row["prompt_text"]),
                "enabled": bool(row["enabled"]),
            }
            for row in rows
        ]

    def list_anime_characters(self, *, list_name: str | None = None, include_disabled: bool = False) -> list[dict[str, object]]:
        conditions = ["(? = 1 OR enabled = 1)"]
        params: list[object] = [1 if include_disabled else 0]
        if list_name:
            conditions.append("list_name = ?")
            params.append(list_name)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, list_name, name, description, enabled
                FROM anime_character
                WHERE {' AND '.join(conditions)}
                ORDER BY list_name, name, id
                """,
                params,
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "list_name": str(row["list_name"]),
                "name": str(row["name"]),
                "description": str(row["description"] or ""),
                "enabled": bool(row["enabled"]),
            }
            for row in rows
        ]

    def delete_anime_character(self, *, character_id: int) -> None:
        with get_connection() as conn:
            with conn:
                conn.execute("DELETE FROM anime_character WHERE id = ?", (character_id,))

    def delete_anime_character_list(self, *, list_name: str) -> None:
        with get_connection() as conn:
            with conn:
                conn.execute("DELETE FROM anime_character WHERE list_name = ?", (list_name,))

    def delete_anime_prompt(self, *, prompt_id: int) -> None:
        with get_connection() as conn:
            with conn:
                conn.execute("DELETE FROM anime_prompt WHERE id = ?", (prompt_id,))

    def save_anime_character_list(self, *, list_name: str, characters: list[str]) -> int:
        cleaned = []
        seen = set()
        for character in characters:
            raw = str(character).strip()
            name = raw
            description = ""
            if raw.startswith("{"):
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
                if isinstance(data, dict):
                    name = str(data.get("name") or "").strip()
                    description = str(data.get("description") or "").strip()
            key = name.lower()
            if name and key not in seen:
                cleaned.append((name, description))
                seen.add(key)
        if not list_name.strip() or not cleaned:
            return 0
        with get_connection() as conn:
            with conn:
                conn.execute(
                    "UPDATE anime_character SET enabled = 0, updated_at = datetime('now') WHERE list_name = ?",
                    (list_name.strip(),),
                )
                for name, description in cleaned:
                    conn.execute(
                        """
                        INSERT INTO anime_character (list_name, name, description, enabled)
                        VALUES (?, ?, ?, 1)
                        ON CONFLICT(list_name, name) DO UPDATE SET
                            description = excluded.description,
                            enabled = 1,
                            updated_at = datetime('now')
                        """,
                        (list_name.strip(), name, description),
                    )
        return len(cleaned)

    def save_anime_character(
        self,
        *,
        character_id: int | None,
        list_name: str,
        name: str,
        description: str = "",
        enabled: bool = True,
    ) -> int:
        with get_connection() as conn:
            with conn:
                if character_id:
                    conn.execute(
                        """
                        UPDATE anime_character
                        SET list_name = ?, name = ?, description = ?, enabled = ?, updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (list_name, name, description, 1 if enabled else 0, character_id),
                    )
                    return int(character_id)
                cur = conn.execute(
                    """
                    INSERT INTO anime_character (list_name, name, description, enabled)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(list_name, name) DO UPDATE SET
                        description = excluded.description,
                        enabled = excluded.enabled,
                        updated_at = datetime('now')
                    RETURNING id
                    """,
                    (list_name, name, description, 1 if enabled else 0),
                )
                return int(cur.fetchone()["id"])

    def save_anime_prompt(
        self,
        *,
        prompt_id: int | None,
        title: str,
        prompt_text: str,
        enabled: bool,
    ) -> int:
        with get_connection() as conn:
            with conn:
                if prompt_id:
                    conn.execute(
                        """
                        UPDATE anime_prompt
                        SET title = ?, prompt_text = ?, enabled = ?, updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (title, prompt_text, 1 if enabled else 0, prompt_id),
                    )
                    return int(prompt_id)
                cur = conn.execute(
                    """
                    INSERT INTO anime_prompt (title, prompt_text, enabled)
                    VALUES (?, ?, ?)
                    ON CONFLICT(title, prompt_text) DO UPDATE SET
                        enabled = excluded.enabled,
                        updated_at = datetime('now')
                    RETURNING id
                    """,
                    (title, prompt_text, 1 if enabled else 0),
                )
                return int(cur.fetchone()["id"])
