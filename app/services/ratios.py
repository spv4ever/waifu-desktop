from __future__ import annotations

from typing import Any


def resolve_size(ratios: dict[str, Any], ratio: str, fallback_w: int, fallback_h: int) -> tuple[int, int]:
    if ratio in ratios:
        w, h = ratios[ratio]
        return int(w), int(h)
    return int(fallback_w), int(fallback_h)
