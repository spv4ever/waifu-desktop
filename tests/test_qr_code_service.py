from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.services.qr_code_service import InvalidQrUrl, QrCodeService, normalize_web_url


def test_normalize_web_url_adds_https_and_preserves_link_parts():
    assert normalize_web_url("example.com/path?q=waifu#result") == (
        "https://example.com/path?q=waifu#result"
    )


@pytest.mark.parametrize("value", ["", "javascript:alert(1)", "https://invalid", "ftp://example.com"])
def test_normalize_web_url_rejects_non_web_links(value: str):
    with pytest.raises(InvalidQrUrl):
        normalize_web_url(value)


def test_generate_png_creates_a_clean_square_qr():
    normalized_url, png_data = QrCodeService().generate_png("https://example.com/waifu")

    image = Image.open(BytesIO(png_data))
    assert normalized_url == "https://example.com/waifu"
    assert image.format == "PNG"
    assert image.width == image.height
    assert 600 <= image.width <= 720
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getbbox() == (0, 0, image.width, image.height)


def test_save_png_adds_extension(tmp_path):
    _, png_data = QrCodeService().generate_png("example.com")
    saved_path = QrCodeService().save_png(png_data, tmp_path / "my-code")

    assert saved_path == tmp_path / "my-code.png"
    assert saved_path.read_bytes() == png_data
