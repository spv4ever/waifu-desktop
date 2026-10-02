from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtGui", exc_type=ImportError)

from PySide6.QtCore import QRectF

from app.data.product_3d_repository import Product3D
from app.services.product_3d_report import Product3DReport, format_page_number


def test_page_number_includes_current_and_total_pages() -> None:
    assert format_page_number(2, 5) == "Página 2 de 5"


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


def test_pdf_contains_current_and_total_page_numbers(tmp_path: Path) -> None:
    products = [
        Product3D(
            id=index,
            category="Figuras",
            description=f"Producto {index}",
            cost_cents=100,
            pvp_cents=200,
            stock=1,
        )
        for index in range(100)
    ]
    destination = tmp_path / "varias-paginas.pdf"

    Product3DReport().generate(destination, products, stock_only=False)

    contents = destination.read_bytes()
    assert contents.startswith(b"%PDF")
    assert contents.count(b"/Type /Page") > 2


def test_product_rows_are_not_bold_after_a_page_break() -> None:
    class PageLayout:
        def paintRectPixels(self, resolution: int) -> QRectF:
            return QRectF(0, 0, 1684, 1191)

    class Writer:
        def pageLayout(self) -> PageLayout:
            return PageLayout()

        def resolution(self) -> int:
            return 144

        def newPage(self) -> None:
            pass

    class Painter:
        def __init__(self) -> None:
            self.font_is_bold = False
            self.product_text_weights: list[bool] = []

        def setFont(self, font) -> None:
            self.font_is_bold = font.bold()

        def drawText(self, *args) -> None:
            text = args[-1]
            if isinstance(text, str) and text.startswith("Producto "):
                self.product_text_weights.append(self.font_is_bold)

        def setPen(self, pen) -> None:
            pass

        def fillRect(self, rect, color) -> None:
            pass

        def drawLine(self, *args) -> None:
            pass

    products = [
        Product3D(
            id=index,
            category="Figuras",
            description=f"Producto {index}",
            cost_cents=100,
            pvp_cents=200,
            stock=1,
        )
        for index in range(30)
    ]
    painter = Painter()

    Product3DReport()._paint(painter, Writer(), products, stock_only=False)

    assert len(painter.product_text_weights) == len(products)
    assert painter.product_text_weights == [False] * len(products)
