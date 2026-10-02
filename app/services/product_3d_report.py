from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from app.data.product_3d_repository import Product3D


def format_euros(cents: int) -> str:
    return f"{cents / 100:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


class Product3DReport:
    """Creates a printable A4 landscape delivery note from inventory rows."""

    def generate(self, destination: str | Path, products: Sequence[Product3D], *, stock_only: bool) -> Path:
        path = Path(destination)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        path.parent.mkdir(parents=True, exist_ok=True)

        writer = QPdfWriter(str(path))
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setPageOrientation(QPageLayout.Landscape)
        writer.setResolution(144)
        writer.setTitle("Albarán de productos 3D")
        painter = QPainter(writer)
        if not painter.isActive():
            raise OSError(f"No se pudo crear el PDF: {path}")

        try:
            self._paint(painter, writer, products, stock_only=stock_only)
        finally:
            painter.end()
        return path

    def _paint(self, painter: QPainter, writer: QPdfWriter, products: Sequence[Product3D], *, stock_only: bool) -> None:
        page = writer.pageLayout().paintRectPixels(writer.resolution())
        margin, row_h = 55, 43
        widths = (90, 260, 650, 180, 180, 120)
        headers = ("ID", "Categoría", "Descripción", "Coste", "PVP", "Stock")
        y = margin

        def page_header(continued: bool = False) -> float:
            nonlocal y
            painter.setPen(QColor("#172033"))
            painter.setFont(QFont("Arial", 17, QFont.Bold))
            painter.drawText(margin, y + 28, "ALBARÁN · PRODUCTOS 3D" + (" (continuación)" if continued else ""))
            painter.setFont(QFont("Arial", 9))
            scope = "Productos con stock" if stock_only else "Listado completo"
            painter.drawText(margin, y + 55, f"{scope} · Generado: {datetime.now():%d/%m/%Y %H:%M}")
            y += 82
            painter.fillRect(QRectF(margin, y, sum(widths), row_h), QColor("#334155"))
            painter.setPen(Qt.white)
            painter.setFont(QFont("Arial", 9, QFont.Bold))
            x = margin
            for label, width in zip(headers, widths):
                painter.drawText(QRectF(x + 7, y, width - 14, row_h), Qt.AlignVCenter | Qt.AlignLeft, label)
                x += width
            y += row_h
            return y

        page_header()
        painter.setFont(QFont("Arial", 9))
        for index, product in enumerate(products):
            if y + row_h + 70 > page.bottom():
                writer.newPage()
                y = margin
                page_header(True)
            if index % 2:
                painter.fillRect(QRectF(margin, y, sum(widths), row_h), QColor("#f1f5f9"))
            painter.setPen(QPen(QColor("#cbd5e1"), 1))
            painter.drawLine(margin, int(y + row_h), margin + sum(widths), int(y + row_h))
            values = (
                str(product.id), product.category, product.description,
                format_euros(product.cost_cents), format_euros(product.pvp_cents), str(product.stock),
            )
            x = margin
            painter.setPen(QColor("#172033"))
            for value, width in zip(values, widths):
                alignment = Qt.AlignVCenter | (Qt.AlignRight if value in values[3:] else Qt.AlignLeft)
                painter.drawText(QRectF(x + 7, y, width - 14, row_h), alignment, value)
                x += width
            y += row_h

        painter.setFont(QFont("Arial", 9, QFont.Bold))
        painter.drawText(
            QRectF(margin, y + 15, sum(widths), 35), Qt.AlignRight,
            f"Referencias: {len(products)}     Unidades totales: {sum(p.stock for p in products)}",
        )
