from __future__ import annotations

from pathlib import Path


try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # pragma: no cover - dependency guard for minimal environments
    Image = None  # type: ignore[assignment]
    UnidentifiedImageError = OSError  # type: ignore[assignment]


def validate_image_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"Imagen no encontrada: {path}")

    if path.stat().st_size == 0:
        raise ValueError(f"Imagen vacía o corrupta: {path.name}")

    with path.open("rb") as handle:
        header = handle.read(16)

    if not (_is_png(header) or _is_jpeg(header) or _is_gif(header) or _is_bmp(header) or _is_webp(header)):
        raise ValueError(f"Formato de imagen no válido: {path.name}")

    if Image is None:
        return

    try:
        with Image.open(path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"Imagen inválida o corrupta: {path.name}") from exc


def _is_png(header: bytes) -> bool:
    return header.startswith(b"\x89PNG\r\n\x1a\n")


def _is_jpeg(header: bytes) -> bool:
    return header.startswith(b"\xff\xd8\xff")


def _is_gif(header: bytes) -> bool:
    return header.startswith(b"GIF87a") or header.startswith(b"GIF89a")


def _is_bmp(header: bytes) -> bool:
    return header.startswith(b"BM")


def _is_webp(header: bytes) -> bool:
    return len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP"
