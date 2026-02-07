from __future__ import annotations

from typing import Any

SAVE_NODE_BASE = "19"
SAVE_NODE_UPSCALE = "52"
SAVE_NODE_DOLLIMAGESZ_BASE = "9"


def _pick_first_image(output: dict[str, Any]) -> dict[str, Any] | None:
    """
    output típico: {"images":[{"filename":"...", "subfolder":"...", "type":"output"}, ...]}
    """
    images = output.get("images")
    if not images or not isinstance(images, list):
        return None
    first = images[0]
    return first if isinstance(first, dict) else None


def extract_base_and_upscale(
    entry: dict[str, Any], *, workflow_key: str | None = None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    entry = history[prompt_id]
    Devuelve (base_image, upscale_image) como dict con filename/subfolder/type.
    """
    outputs = entry.get("outputs") or {}

    base_node = SAVE_NODE_BASE
    upscale_node = SAVE_NODE_UPSCALE
    if workflow_key == "dollimagesz":
        base_node = SAVE_NODE_DOLLIMAGESZ_BASE
        upscale_node = None

    base_out = outputs.get(base_node) or {}
    up_out = outputs.get(upscale_node) if upscale_node else None

    base_img = _pick_first_image(base_out) if isinstance(base_out, dict) else None
    up_img = _pick_first_image(up_out) if isinstance(up_out, dict) else None

    if base_img or up_img:
        return base_img, up_img

    for out in outputs.values():
        if isinstance(out, dict):
            fallback = _pick_first_image(out)
            if fallback:
                return fallback, None

    return None, None
