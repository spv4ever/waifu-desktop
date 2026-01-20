from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
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
    def variants(self) -> dict[str, Any]:
        return self.raw.get("variants", {})


def load_app_config(path: Path | None = None) -> AppConfig:
    path = path or Path("resources") / "config" / "app_config.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AppConfig(raw=data)
