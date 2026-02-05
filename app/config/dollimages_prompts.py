from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def _normalize_typology(value: str | None) -> str:
    typology = str(value or "normal").strip().lower()
    if typology not in {"normal", "sfw", "nsfw"}:
        return "normal"
    return typology


def _normalize_enabled(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def load_dollimages_prompts(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "prompts" in data:
        data = data.get("prompts")

    if not isinstance(data, list):
        raise ValueError("dollimages_prompts.json inválido: se esperaba una lista o {'prompts': []}")

    prompts: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        prompt_text = str(item.get("prompt_text", "")).strip()
        if not title or not prompt_text:
            continue
        group_name = str(item.get("group_name", "") or item.get("group", "")).strip()
        typology = _normalize_typology(item.get("typology"))
        enabled = _normalize_enabled(item.get("enabled", True))
        prompts.append(
            {
                "group_name": group_name,
                "title": title,
                "prompt_text": prompt_text,
                "typology": typology,
                "enabled": enabled,
            }
        )
    return prompts
