from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.data.storage import get_store

@dataclass(frozen=True)
class WaifuCatalog:
    raw: dict[str, Any]

    @property
    def defaults(self) -> dict[str, Any]:
        return self.raw.get("defaults", {})

    @property
    def ratios(self) -> dict[str, Any]:
        return self.raw.get("ratios", {})

    @property
    def categories(self) -> dict[str, Any]:
        return self.raw.get("categories", {})

    @property
    def combinations(self) -> dict[str, Any]:
        return self.raw.get("combinations", {})

    @property
    def wardrobe(self) -> dict[str, Any]:
        return self.raw.get("wardrobe", {})

    @property
    def footwear(self) -> dict[str, Any]:
        return self.raw.get("footwear", {})

    @property
    def pose(self) -> dict[str, Any]:
        return self.raw.get("pose", {})

    @property
    def background(self) -> dict[str, Any]:
        return self.raw.get("background", {})

    @property
    def lighting(self) -> dict[str, Any]:
        return self.raw.get("lighting", {})


def load_waifu_catalog(path: str | Path = "resources/config/waifu_catalog.yaml") -> WaifuCatalog:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("waifu_catalog.yaml inválido: se esperaba un dict raíz")
    store = get_store()
    store.ensure_prompt_base_seeded(data.get("categories", {}))
    store.ensure_prompt_variations_seeded(data)
    bases = store.list_prompt_bases(include_disabled=False)

    categories: dict[str, Any] = {}
    for base in bases:
        categories[base.key] = {
            "label": base.label,
            "base_prompt": base.base_prompt,
            "allowed_ratios": base.allowed_ratios,
            "enabled": base.enabled,
            "kind": base.kind,
        }

    data = dict(data)
    data["categories"] = categories
    data.update(store.fetch_prompt_variations_tree())
    return WaifuCatalog(raw=data)
