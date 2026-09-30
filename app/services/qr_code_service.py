from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import qrcode
from qrcode.constants import ERROR_CORRECT_M


class InvalidQrUrl(ValueError):
    """Raised when a value cannot be represented as a web link QR code."""


def normalize_web_url(value: str) -> str:
    """Return a normalized HTTP(S) URL suitable for embedding in a QR code."""
    url = value.strip()
    if not url:
        raise InvalidQrUrl("Introduce un enlace para generar el código QR.")
    if any(character in url for character in "\r\n\t"):
        raise InvalidQrUrl("El enlace no puede contener saltos de línea ni tabulaciones.")
    if "://" not in url:
        url = f"https://{url}"

    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise InvalidQrUrl("Introduce un enlace web válido que empiece por http:// o https://.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidQrUrl("El puerto del enlace no es válido.") from exc

    hostname = parsed.hostname.encode("idna").decode("ascii")
    if "." not in hostname and hostname != "localhost":
        raise InvalidQrUrl("El enlace debe incluir un dominio válido.")
    if parsed.username or parsed.password:
        raise InvalidQrUrl("El enlace no puede incluir usuario ni contraseña.")

    netloc = hostname
    if ":" in hostname and not hostname.startswith("["):
        netloc = f"[{hostname}]"
    if port is not None:
        netloc = f"{netloc}:{port}"

    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, parsed.query, parsed.fragment))


class QrCodeService:
    def generate_png(self, url: str, *, pixels: int = 720) -> tuple[str, bytes]:
        normalized_url = normalize_web_url(url)
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(normalized_url)
        qr.make(fit=True)
        # Keep every module on an exact pixel grid so the exported image stays
        # crisp and reliably scannable instead of stretching it after rendering.
        qr.box_size = max(1, pixels // (qr.modules_count + (qr.border * 2)))
        image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return normalized_url, output.getvalue()

    def save_png(self, png_data: bytes, destination: str | Path) -> Path:
        path = Path(destination).expanduser()
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_data)
        return path
