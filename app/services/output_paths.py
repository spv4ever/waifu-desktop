from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.config.settings import settings


def _normalize_subfolder(subfolder: str) -> str:
    # history a veces viene con \\, lo normalizamos
    return subfolder.replace("\\", os.sep).replace("/", os.sep).strip(os.sep)


def build_output_path(image_json: dict[str, Any]) -> Path:
    """
    image_json = {"filename": "...", "subfolder": "...", "type": "output"}
    Devuelve el path absoluto esperado en disco.
    """
    base_dir = Path(settings.comfyui_output_dir)
    subfolder = _normalize_subfolder(image_json.get("subfolder", ""))
    filename = image_json.get("filename", "")
    return base_dir / subfolder / filename
