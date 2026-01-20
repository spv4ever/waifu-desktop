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
    has_base: bool
    has_upscale: bool
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


def fetch_prompts(
    *,
    limit: int = 50,
    category: str | None = None,
    variant: str | None = None,
    status: str | None = None,
    ratio: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
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
                COALESCE(updated_at, created_at) AS datestamp
            FROM prompt_item
            ORDER BY id DESC
            """
        ).fetchall()

    result: list[PromptRow] = []
    for r in rows:
        row_status = str(r["status"])
        category_value, variant_value = _extract_category_variant(r["meta_json"])
        ratio_value = _extract_ratio(r["meta_json"])
        row_datestamp = str(r["datestamp"]) if r["datestamp"] else ""
        row_dt = _parse_db_datetime(row_datestamp) if row_datestamp else None

        if category and category_value != category:
            continue
        if variant and variant_value != variant:
            continue
        if status and row_status != status:
            continue
        if ratio and ratio_value != ratio:
            continue
        if dt_from and (row_dt is None or row_dt < dt_from):
            continue
        if dt_to and (row_dt is None or row_dt > dt_to):
            continue

        result.append(
            PromptRow(
                id=int(r["id"]),
                title=str(r["title"]),
                prompt_text=str(r["prompt_text"]),
                status=row_status,
                category=category_value,
                variant=variant_value,
                ratio=ratio_value,
                has_base=bool(r["base_image_json"]),
                has_upscale=bool(r["upscale_image_json"]),
                datestamp=_format_datestamp(row_datestamp),
            )
        )
        if len(result) >= limit:
            break
    return result


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
