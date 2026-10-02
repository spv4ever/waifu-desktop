from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtGui", exc_type=ImportError)

from app.data.product_3d_repository import Product3D
from app.services.product_3d_report import Product3DReport


def test_pdf_omits_cost_by_default_and_includes_it_on_request(tmp_path: Path) -> None:
    product = Product3D(
        id=1,
        category="Figuras",
        description="Dragón",
        cost_cents=12345,
        pvp_cents=67890,
        stock=2,
    )
    default_pdf = tmp_path / "sin-coste.pdf"
    cost_pdf = tmp_path / "con-coste.pdf"

    Product3DReport().generate(default_pdf, [product], stock_only=False)
    Product3DReport().generate(cost_pdf, [product], stock_only=False, include_cost=True)

    assert default_pdf.read_bytes().startswith(b"%PDF")
    assert cost_pdf.read_bytes().startswith(b"%PDF")
    assert default_pdf.read_bytes() != cost_pdf.read_bytes()
