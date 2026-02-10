from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.config.settings import settings


def _normalize_subfolder(subfolder: str) -> str:
    # history a veces viene con \\, lo normalizamos
    return subfolder.replace("\\", os.sep).replace("/", os.sep).strip(os.sep)


def _resolve_base_dir(workflow_key: str | None) -> Path:
    if workflow_key == "image2vid" and settings.comfyui_image2vid_output_dir:
        return Path(settings.comfyui_image2vid_output_dir)
    if workflow_key in {"dollimages", "dollimagesz"} and settings.comfyui_dollimages_output_dir:
        return Path(settings.comfyui_dollimages_output_dir)
    return Path(settings.comfyui_output_dir)


def build_output_path(image_json: dict[str, Any], *, workflow_key: str | None = None) -> Path:
    """
    image_json = {"filename": "...", "subfolder": "...", "type": "output"}
    Devuelve el path absoluto esperado en disco.
    """
    base_dir = _resolve_base_dir(workflow_key)
    subfolder = _normalize_subfolder(image_json.get("subfolder", ""))
    filename = image_json.get("filename", "")
    return base_dir / subfolder / filename
