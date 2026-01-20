from __future__ import annotations

from typing import Any

# IDs de tus SaveImage según tu workflow:
# - 19: SaveImage (base)
# - 52: SaveImage (upscale)
SAVE_NODE_BASE = "19"
SAVE_NODE_UPSCALE = "52"


def _pick_first_image(output: dict[str, Any]) -> dict[str, Any] | None:
    """
    output típico: {"images":[{"filename":"...", "subfolder":"...", "type":"output"}, ...]}
    """
    images = output.get("images")
    if not images or not isinstance(images, list):
        return None
    first = images[0]
    return first if isinstance(first, dict) else None


def extract_base_and_upscale(entry: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    entry = history[prompt_id]
    Devuelve (base_image, upscale_image) como dict con filename/subfolder/type.
    """
    outputs = entry.get("outputs") or {}
    base_out = outputs.get(SAVE_NODE_BASE) or {}
    up_out = outputs.get(SAVE_NODE_UPSCALE) or {}

    base_img = _pick_first_image(base_out) if isinstance(base_out, dict) else None
    up_img = _pick_first_image(up_out) if isinstance(up_out, dict) else None

    return base_img, up_img
