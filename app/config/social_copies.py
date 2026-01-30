from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_social_copies(path: str | Path = "resources/config/social_copies.yaml") -> list[dict[str, str]]:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("social_copies.yaml inválido: se esperaba una lista")

    copies: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        hashtags = str(item.get("hashtags", "")).strip()
        if not text:
            continue
        copies.append({"text": text, "hashtags": hashtags})
    return copies
