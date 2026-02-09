from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

import requests

from app.config.settings import settings


class CloudinaryUploadError(RuntimeError):
    pass


def _build_signature(params: dict[str, str], *, api_secret: str) -> str:
    payload = "&".join(f"{key}={params[key]}" for key in sorted(params))
    payload = f"{payload}{api_secret}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _ensure_dollimages_enabled() -> tuple[bool, str | None]:
    if not settings.cloudinary_cloud_name:
        return False, "CLOUDINARY_CLOUD_NAME no configurado"
    if not settings.cloudinary_api_key:
        return False, "CLOUDINARY_API_KEY no configurado"
    if not settings.cloudinary_api_secret:
        return False, "CLOUDINARY_API_SECRET no configurado"
    return True, None


def _ensure_waifu_enabled() -> tuple[bool, str | None]:
    if not settings.cloudinary_waifu_cloud_name:
        return False, "CLOUDINARY_WAIFU_CLOUD_NAME no configurado"
    if not settings.cloudinary_waifu_api_key:
        return False, "CLOUDINARY_WAIFU_API_KEY no configurado"
    if not settings.cloudinary_waifu_api_secret:
        return False, "CLOUDINARY_WAIFU_API_SECRET no configurado"
    return True, None


def upload_dollimages_image(
    *,
    image_path: Path,
    title: str,
    checkpoint: str | None,
    version: str | None,
    created_at: str,
) -> dict[str, Any]:
    enabled, reason = _ensure_dollimages_enabled()
    if not enabled:
        raise CloudinaryUploadError(reason or "Cloudinary no configurado")

    if not image_path.exists():
        raise CloudinaryUploadError(f"No existe el archivo: {image_path}")

    cloud_name = settings.cloudinary_cloud_name
    api_key = settings.cloudinary_api_key
    api_secret = settings.cloudinary_api_secret
    timestamp = str(int(time.time()))
    folder = settings.cloudinary_dollimages_folder or "dollimages"

    context_parts = [
        f"title={title}",
        f"checkpoint={checkpoint or ''}",
        f"version={version or ''}",
        f"created_at={created_at}",
    ]
    context = "|".join(context_parts)

    signature_params = {
        "context": context,
        "folder": folder,
        "timestamp": timestamp,
    }
    signature = _build_signature(signature_params, api_secret=api_secret)
    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

    with image_path.open("rb") as handle:
        response = requests.post(
            url,
            data={
                "api_key": api_key,
                "timestamp": timestamp,
                "folder": folder,
                "context": context,
                "signature": signature,
            },
            files={"file": handle},
            timeout=120,
        )

    if response.status_code >= 400:
        raise CloudinaryUploadError(
            f"Cloudinary error {response.status_code}: {response.text}"
        )

    payload = response.json()
    if not isinstance(payload, dict) or "secure_url" not in payload:
        raise CloudinaryUploadError("Respuesta inválida de Cloudinary")
    return payload


def upload_waifu_image(
    *,
    image_path: Path,
    title: str,
    checkpoint: str | None,
    version: str | None,
    created_at: str,
) -> dict[str, Any]:
    enabled, reason = _ensure_waifu_enabled()
    if not enabled:
        raise CloudinaryUploadError(reason or "Cloudinary no configurado")

    if not image_path.exists():
        raise CloudinaryUploadError(f"No existe el archivo: {image_path}")

    cloud_name = settings.cloudinary_waifu_cloud_name
    api_key = settings.cloudinary_waifu_api_key
    api_secret = settings.cloudinary_waifu_api_secret
    timestamp = str(int(time.time()))
    folder = settings.cloudinary_waifu_folder or "waifu"

    context_parts = [
        f"title={title}",
        f"checkpoint={checkpoint or ''}",
        f"version={version or ''}",
        f"created_at={created_at}",
    ]
    context = "|".join(context_parts)

    signature_params = {
        "context": context,
        "folder": folder,
        "timestamp": timestamp,
    }
    signature = _build_signature(signature_params, api_secret=api_secret)
    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"

    with image_path.open("rb") as handle:
        response = requests.post(
            url,
            data={
                "api_key": api_key,
                "timestamp": timestamp,
                "folder": folder,
                "context": context,
                "signature": signature,
            },
            files={"file": handle},
            timeout=120,
        )

    if response.status_code >= 400:
        raise CloudinaryUploadError(
            f"Cloudinary error {response.status_code}: {response.text}"
        )

    payload = response.json()
    if not isinstance(payload, dict) or "secure_url" not in payload:
        raise CloudinaryUploadError("Respuesta inválida de Cloudinary")
    return payload
