from __future__ import annotations

import json
from typing import Any

SAVE_NODE_BASE = "19"
SAVE_NODE_UPSCALE = "52"
SAVE_NODE_DOLLIMAGESZ_BASE = "9"
SAVE_NODE_IMAGE2VID_VIDEO = "108"
SAVE_NODE_KREA2_BASE = "363"
SAVE_NODE_KREA2_UPSCALE = "364"


def _pick_images(output: dict[str, Any]) -> list[dict[str, Any]]:
    """
    output típico: {"images":[{"filename":"...", "subfolder":"...", "type":"output"}, ...]}
    """
    images = output.get("images")
    if not images or not isinstance(images, list):
        return []
    return [image for image in images if isinstance(image, dict)]


def _pick_first_image(output: dict[str, Any]) -> dict[str, Any] | None:
    images = _pick_images(output)
    return images[0] if images else None


def _pick_first_media(output: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("videos", "gifs", "images"):
        media = output.get(key)
        if isinstance(media, list) and media:
            first = media[0]
            if isinstance(first, dict):
                return first
    return None


def has_rendered_media(entry: dict[str, Any]) -> bool:
    outputs = entry.get("outputs") or {}
    for out in outputs.values():
        if isinstance(out, dict) and _pick_first_media(out):
            return True
    return False


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
    elif workflow_key in {"krea2", "krea2_v2"}:
        base_node = SAVE_NODE_KREA2_BASE
        upscale_node = SAVE_NODE_KREA2_UPSCALE

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


def extract_base_and_upscale_images(
    entry: dict[str, Any], *, workflow_key: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Devuelve todas las imágenes base/upscale publicadas por los nodos de guardado."""
    outputs = entry.get("outputs") or {}

    base_node = SAVE_NODE_BASE
    upscale_node = SAVE_NODE_UPSCALE
    if workflow_key == "dollimagesz":
        base_node = SAVE_NODE_DOLLIMAGESZ_BASE
        upscale_node = None
    elif workflow_key in {"krea2", "krea2_v2"}:
        base_node = SAVE_NODE_KREA2_BASE
        upscale_node = SAVE_NODE_KREA2_UPSCALE

    base_out = outputs.get(base_node) or {}
    up_out = outputs.get(upscale_node) if upscale_node else None

    base_images = _pick_images(base_out) if isinstance(base_out, dict) else []
    up_images = _pick_images(up_out) if isinstance(up_out, dict) else []

    if base_images or up_images:
        return base_images, up_images

    for out in outputs.values():
        if isinstance(out, dict):
            fallback = _pick_images(out)
            if fallback:
                return fallback, []

    return [], []


def extract_video_output(entry: dict[str, Any]) -> dict[str, Any] | None:
    outputs = entry.get("outputs") or {}

    preferred = outputs.get(SAVE_NODE_IMAGE2VID_VIDEO)
    if isinstance(preferred, dict):
        media = _pick_first_media(preferred)
        if media:
            return media

    for out in outputs.values():
        if isinstance(out, dict):
            media = _pick_first_media(out)
            if media and str(media.get("filename", "")).lower().endswith((".mp4", ".webm", ".mov", ".mkv", ".gif")):
                return media

    for out in outputs.values():
        if isinstance(out, dict):
            media = _pick_first_media(out)
            if media:
                return media

    return None


def extract_saved_video_output(
    *, base_media_json: str | None, history_json: str | None
) -> dict[str, Any] | None:
    """Resolve a video saved directly on a prompt or in a legacy queue history."""
    if base_media_json:
        try:
            media = json.loads(base_media_json)
        except (TypeError, ValueError):
            media = None
        if isinstance(media, dict) and str(media.get("filename", "")).lower().endswith(
            (".mp4", ".webm", ".mov", ".mkv", ".gif")
        ):
            return media

    if history_json:
        try:
            history = json.loads(history_json)
        except (TypeError, ValueError):
            return None
        if isinstance(history, dict):
            return extract_video_output(history)
    return None
