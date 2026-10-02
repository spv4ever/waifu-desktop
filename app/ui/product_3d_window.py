from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.data.db import get_connection
from app.data.product_3d_repository import Product3D, Product3DRepository
from app.services.product_3d_report import Product3DReport, format_euros


class ProductEditorDialog(QDialog):
    def __init__(
        self, parent: QWidget, product: Product3D | None = None, *, duplicate: bool = False,
    ) -> None:
        super().__init__(parent)
        if duplicate:
            self.setWindowTitle("Duplicar producto 3D")
        else:
            self.setWindowTitle("Modificar producto 3D" if product else "Nuevo producto 3D")
        form = QFormLayout(self)
        self.category = QLineEdit(product.category if product else "")
        self.description = QLineEdit(product.description if product else "")
        self.cost = self._money(product.cost_cents if product else 0)
        self.pvp = self._money(product.pvp_cents if product else 0)
        self.stock = QSpinBox()
        self.stock.setRange(0, 1_000_000)
        self.stock.setValue(product.stock if product else 0)
        form.addRow("Categoría *", self.category)
        form.addRow("Descripción *", self.description)
        form.addRow("Coste", self.cost)
        form.addRow("PVP", self.pvp)
        form.addRow("Stock", self.stock)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_validated)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @staticmethod
    def _money(cents: int) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(0, 10_000_000)
        field.setDecimals(2)
        field.setSuffix(" €")
        field.setValue(cents / 100)
        return field

    def _accept_validated(self) -> None:
        if not self.category.text().strip() or not self.description.text().strip():
            QMessageBox.warning(self, "Datos incompletos", "La categoría y la descripción son obligatorias.")
            return
        self.accept()

    def values(self) -> dict[str, str | int]:
        cents = lambda value: int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return {
            "category": self.category.text().strip(), "description": self.description.text().strip(),
            "cost_cents": cents(self.cost.value()), "pvp_cents": cents(self.pvp.value()),
            "stock": self.stock.value(),
        }


class Product3DWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Waifu Desktop — Productos 3D")
        self.resize(1050, 680)
        self.repository = Product3DRepository()
        self.report = Product3DReport()
        self.products: list[Product3D] = []

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("Productos 3D")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("Inventario de creaciones para mercadillos"))

        filters = QHBoxLayout()
        self.category_filter = QLineEdit()
        self.category_filter.setPlaceholderText("Filtrar por categoría…")
        self.description_filter = QLineEdit()
        self.description_filter.setPlaceholderText("Filtrar por descripción…")
        self.stock_filter = QCheckBox("Solo con stock")
        for field in (self.category_filter, self.description_filter):
            field.textChanged.connect(self.refresh)
            filters.addWidget(field)
        self.stock_filter.toggled.connect(self.refresh)
        filters.addWidget(self.stock_filter)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("ID", "Categoría", "Descripción", "Coste", "PVP", "Stock"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_product)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        for label, callback in (
            ("Nuevo", self.new_product),
            ("Duplicar", self.duplicate_product),
            ("Modificar", self.edit_product),
            ("Borrar", self.delete_product),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        pdf_stock = QPushButton("Albarán PDF · con stock")
        pdf_stock.clicked.connect(lambda: self.export_pdf(True))
        pdf_all = QPushButton("Albarán PDF · listado completo")
        pdf_all.setObjectName("PrimaryButton")
        pdf_all.clicked.connect(lambda: self.export_pdf(False))
        actions.addWidget(pdf_stock)
        actions.addWidget(pdf_all)
        layout.addLayout(actions)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.refresh()

    def refresh(self) -> None:
        with get_connection() as conn:
            self.products = self.repository.list(
                conn, category=self.category_filter.text(), description=self.description_filter.text(),
                in_stock_only=self.stock_filter.isChecked(),
            )
        self.table.setRowCount(len(self.products))
        for row, product in enumerate(self.products):
            values = (product.id, product.category, product.description, format_euros(product.cost_cents), format_euros(product.pvp_cents), product.stock)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (0, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, column, item)
        self.status.setText(f"{len(self.products)} referencias · {sum(p.stock for p in self.products)} unidades")

    def _selected(self) -> Product3D | None:
        row = self.table.currentRow()
        return self.products[row] if 0 <= row < len(self.products) else None

    def new_product(self) -> None:
        dialog = ProductEditorDialog(self)
        if dialog.exec() == QDialog.Accepted:
            with get_connection() as conn:
                self.repository.create(conn, **dialog.values())
            self.refresh()

    def edit_product(self, *_args) -> None:
        product = self._selected()
        if product is None:
            QMessageBox.information(self, "Modificar", "Selecciona primero un producto.")
            return
        dialog = ProductEditorDialog(self, product)
        if dialog.exec() == QDialog.Accepted:
            with get_connection() as conn:
                self.repository.update(conn, product.id, **dialog.values())
            self.refresh()

    def duplicate_product(self) -> None:
        product = self._selected()
        if product is None:
            QMessageBox.information(self, "Duplicar", "Selecciona primero un producto.")
            return
        dialog = ProductEditorDialog(self, product, duplicate=True)
        if dialog.exec() == QDialog.Accepted:
            with get_connection() as conn:
                self.repository.create(conn, **dialog.values())
            self.refresh()

    def delete_product(self) -> None:
        product = self._selected()
        if product is None:
            QMessageBox.information(self, "Borrar", "Selecciona primero un producto.")
            return
        if QMessageBox.question(self, "Borrar producto", f"¿Borrar #{product.id} · {product.description}?") != QMessageBox.Yes:
            return
        with get_connection() as conn:
            self.repository.delete(conn, product.id)
        self.refresh()

    def export_pdf(self, stock_only: bool) -> None:
        with get_connection() as conn:
            products = self.repository.list(conn, in_stock_only=stock_only)
        filename, _ = QFileDialog.getSaveFileName(self, "Guardar albarán", "albaran-productos-3d.pdf", "PDF (*.pdf)")
        if not filename:
            return
        try:
            path = self.report.generate(filename, products, stock_only=stock_only)
        except OSError as exc:
            QMessageBox.critical(self, "No se pudo generar el PDF", str(exc))
            return
        QMessageBox.information(self, "Albarán generado", f"PDF guardado en:\n{path}")
