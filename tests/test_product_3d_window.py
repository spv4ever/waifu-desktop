from __future__ import annotations

import os
import sqlite3
from contextlib import nullcontext
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = qt_widgets.QApplication
QDialog = qt_widgets.QDialog
QFileDialog = qt_widgets.QFileDialog
QMessageBox = qt_widgets.QMessageBox

from app.data.product_3d_repository import Product3DRepository
from app.ui import product_3d_window


def test_duplicate_opens_prefilled_product_and_creates_a_new_record(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = Path(__file__).parents[1] / "app/data/schema.sql"
    conn.executescript(schema.read_text(encoding="utf-8"))
    repository = Product3DRepository()
    source_id = repository.create(
        conn,
        category="Figuras",
        description="Dragón",
        cost_cents=250,
        pvp_cents=900,
        stock=2,
    )
    monkeypatch.setattr(product_3d_window, "get_connection", lambda: nullcontext(conn))

    captured = {}

    class DuplicateDialog:
        def __init__(self, _parent, product, *, duplicate=False):
            captured["product"] = product
            captured["duplicate"] = duplicate

        def exec(self):
            return QDialog.Accepted

        def values(self):
            return {
                "category": "Figuras",
                "description": "Dragón retocado",
                "cost_cents": 275,
                "pvp_cents": 950,
                "stock": 1,
            }

    window = product_3d_window.Product3DWindow()
    window.table.selectRow(0)
    monkeypatch.setattr(product_3d_window, "ProductEditorDialog", DuplicateDialog)

    window.duplicate_product()
    app.processEvents()

    assert captured == {"product": window.products[0], "duplicate": True}
    products = repository.list(conn)
    assert [product.id for product in products] == [source_id, source_id + 1]
    assert products[1].description == "Dragón retocado"
    assert products[1].pvp_cents == 950
    window.close()
    conn.close()


def test_pdf_cost_is_hidden_by_default_and_can_be_enabled(monkeypatch, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = Path(__file__).parents[1] / "app/data/schema.sql"
    conn.executescript(schema.read_text(encoding="utf-8"))
    repository = Product3DRepository()
    repository.create(
        conn, category="Figuras", description="Dragón",
        cost_cents=250, pvp_cents=900, stock=2,
    )
    monkeypatch.setattr(product_3d_window, "get_connection", lambda: nullcontext(conn))
    destination = tmp_path / "albaran.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(destination), "PDF (*.pdf)"))
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    captured = []

    class Report:
        def generate(self, filename, products, **options):
            captured.append((filename, products, options))
            return destination

    window = product_3d_window.Product3DWindow()
    window.report = Report()

    assert not window.pdf_cost.isChecked()
    window.export_pdf(False)
    window.pdf_cost.setChecked(True)
    window.export_pdf(True)

    assert captured[0][2] == {"stock_only": False, "include_cost": False}
    assert captured[1][2] == {"stock_only": True, "include_cost": True}
    window.close()
    conn.close()
