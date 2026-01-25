from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.data.db import get_connection


@dataclass(frozen=True)
class PromptRow:
    id: int
    title: str
    prompt_text: str
    status: str
    category: str
    variant: str
    ratio: str
    checkpoint_base: str | None
    checkpoint_refiner: str | None
    has_base: bool
    has_upscale: bool
    progress: int | None
    backend_status: str | None
    datestamp: str


def _extract_category_variant(meta_json: str | None) -> tuple[str, str]:
    if not meta_json:
        return "?", "?"
    try:
        meta = json.loads(meta_json)
        combo = meta.get("combo", {})
        return str(combo.get("category", "?")), str(combo.get("variant", "?"))
    except Exception:
        return "?", "?"


def _extract_ratio(meta_json: str | None) -> str:
    if not meta_json:
        return "?"
    try:
        meta = json.loads(meta_json)
        combo = meta.get("combo", {})
        return str(
            combo.get("ratio_tag")
            or combo.get("ratio_key")
            or combo.get("ratio")
            or meta.get("ratio")
            or "?"
        )
    except Exception:
        return "?"


def _extract_checkpoints(meta_json: str | None) -> tuple[str | None, str | None]:
    if not meta_json:
        return None, None
    try:
        meta = json.loads(meta_json)
        checkpoints = meta.get("checkpoints", {})
        if not isinstance(checkpoints, dict):
            return None, None
        base = checkpoints.get("base")
        refiner = checkpoints.get("refiner")
        return str(base) if base else None, str(refiner) if refiner else None
    except Exception:
        return None, None


def fetch_prompt_filters() -> dict[str, list[str]]:
    categories: set[str] = set()
    variants: set[str] = set()
    ratios: set[str] = set()
    statuses: set[str] = set()

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
        category, variant = _extract_category_variant(r["meta_json"])
        ratio = _extract_ratio(r["meta_json"])
        if category and category != "?":
            categories.add(category)
        if variant and variant != "?":
            variants.add(variant)
        if ratio and ratio != "?":
            ratios.add(ratio)

    return {
        "categories": sorted(categories),
        "variants": sorted(variants),
        "ratios": sorted(ratios),
        "statuses": sorted(statuses),
    }


def fetch_prompt_status_counts() -> dict[str, int]:
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


def fetch_category_production_counts() -> list[tuple[str, int]]:
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
        category, _ = _extract_category_variant(r["meta_json"])
        if not category or category == "?":
            continue
        counts[category] = counts.get(category, 0) + 1

    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def fetch_prompts(
    *,
    limit: int = 50,
    prompt_id: int | None = None,
    category: str | None = None,
    variant: str | None = None,
    status: str | None = None,
    ratio: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort_order: str = "desc",
) -> list[PromptRow]:
    dt_from = _parse_db_datetime(date_from) if date_from else None
    dt_to = _parse_db_datetime(date_to) if date_to else None

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                title,
                prompt_text,
                status,
                meta_json,
                base_image_json,
                upscale_image_json,
                (SELECT progress FROM queue_job WHERE prompt_item_id = prompt_item.id ORDER BY id DESC LIMIT 1) AS job_progress,
                (SELECT backend_status FROM queue_job WHERE prompt_item_id = prompt_item.id ORDER BY id DESC LIMIT 1) AS job_backend_status,
                (SELECT status FROM queue_job WHERE prompt_item_id = prompt_item.id ORDER BY id DESC LIMIT 1) AS job_status,
                COALESCE(updated_at, created_at) AS datestamp
            FROM prompt_item
            ORDER BY id DESC
            """
        ).fetchall()

    result: list[tuple[datetime | None, PromptRow]] = []
    for r in rows:
        row_status = str(r["status"])
        job_progress = r["job_progress"]
        job_status = r["job_status"]
        job_backend_status = r["job_backend_status"]
        category_value, variant_value = _extract_category_variant(r["meta_json"])
        ratio_value = _extract_ratio(r["meta_json"])
        checkpoint_base, checkpoint_refiner = _extract_checkpoints(r["meta_json"])
        row_datestamp = str(r["datestamp"]) if r["datestamp"] else ""
        row_dt = _parse_db_datetime(row_datestamp) if row_datestamp else None
        progress_value = _resolve_progress(row_status, job_status, job_progress)

        if category and category_value != category:
            continue
        if variant and variant_value != variant:
            continue
        if status and row_status != status:
            continue
        if ratio and ratio_value != ratio:
            continue
        if prompt_id is not None and int(r["id"]) != prompt_id:
            continue
        if dt_from and (row_dt is None or row_dt < dt_from):
            continue
        if dt_to and (row_dt is None or row_dt > dt_to):
            continue

        result.append(
            (
                row_dt,
                PromptRow(
                    id=int(r["id"]),
                    title=str(r["title"]),
                    prompt_text=str(r["prompt_text"]),
                    status=row_status,
                    category=category_value,
                    variant=variant_value,
                    ratio=ratio_value,
                    checkpoint_base=checkpoint_base,
                    checkpoint_refiner=checkpoint_refiner,
                    has_base=bool(r["base_image_json"]),
                    has_upscale=bool(r["upscale_image_json"]),
                    progress=progress_value,
                    backend_status=str(job_backend_status) if job_backend_status else None,
                    datestamp=_format_datestamp(row_datestamp),
                ),
            )
        )
    reverse = sort_order.lower() != "asc"
    if reverse:
        sentinel = datetime.min
    else:
        sentinel = datetime.max

    result.sort(key=lambda item: item[0] or sentinel, reverse=reverse)
    return [row for _, row in result[:limit]]


def _parse_db_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_datestamp(value: str | None) -> str:
    dt = _parse_db_datetime(value)
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _resolve_progress(status: str, job_status: str | None, job_progress: int | None) -> int | None:
    if isinstance(job_progress, int) and 0 <= job_progress <= 100:
        return job_progress
    if status == "DONE":
        return 100
    if status in {"QUEUED", "SENT"}:
        return 0
    if job_status in {"PENDING", "RUNNING"}:
        return 0
    return None
