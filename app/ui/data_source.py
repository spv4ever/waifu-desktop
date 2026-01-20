from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.data.db import get_connection


@dataclass(frozen=True)
class PromptRow:
    id: int
    title: str
    status: str
    category: str
    variant: str
    has_base: bool
    has_upscale: bool


def _extract_category_variant(meta_json: str | None) -> tuple[str, str]:
    if not meta_json:
        return "?", "?"
    try:
        meta = json.loads(meta_json)
        combo = meta.get("combo", {})
        return str(combo.get("category", "?")), str(combo.get("variant", "?"))
    except Exception:
        return "?", "?"


def fetch_latest_prompts(limit: int = 50) -> list[PromptRow]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, status, meta_json, base_image_json, upscale_image_json
            FROM prompt_item
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    result: list[PromptRow] = []
    for r in rows:
        category, variant = _extract_category_variant(r["meta_json"])
        result.append(
            PromptRow(
                id=int(r["id"]),
                title=str(r["title"]),
                status=str(r["status"]),
                category=category,
                variant=variant,
                has_base=bool(r["base_image_json"]),
                has_upscale=bool(r["upscale_image_json"]),
            )
        )
    return result
