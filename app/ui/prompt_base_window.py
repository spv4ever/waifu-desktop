from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QCheckBox,
    QLabel,
    QMessageBox,
    QGroupBox,
)

from app.data.repositories import PromptBaseRow
from app.data.storage import get_store


class PromptBaseWindow(QMainWindow):
    catalog_updated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mantenimiento de categorías y personajes")
        self.resize(780, 520)

        self.prompt_base_map: dict[str, PromptBaseRow] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        prompt_base_group = QGroupBox("Prompts base (Categorías / Personajes)")
        prompt_base_layout = QVBoxLayout(prompt_base_group)

        prompt_base_row_one = QHBoxLayout()
        prompt_base_row_one.addWidget(QLabel("Base existente:"))
        self.prompt_base_combo = QComboBox()
        self.prompt_base_combo.setMinimumWidth(200)
        prompt_base_row_one.addWidget(self.prompt_base_combo)

        prompt_base_row_one.addWidget(QLabel("Tipo:"))
        self.prompt_base_kind_combo = QComboBox()
        self.prompt_base_kind_combo.addItem("Categoría", "category")
        self.prompt_base_kind_combo.addItem("Personaje", "character")
        prompt_base_row_one.addWidget(self.prompt_base_kind_combo)

        prompt_base_row_one.addWidget(QLabel("Key:"))
        self.prompt_base_key_input = QLineEdit()
        self.prompt_base_key_input.setPlaceholderText("clave_unica")
        self.prompt_base_key_input.setMinimumWidth(140)
        prompt_base_row_one.addWidget(self.prompt_base_key_input)

        prompt_base_row_one.addWidget(QLabel("Label:"))
        self.prompt_base_label_input = QLineEdit()
        self.prompt_base_label_input.setPlaceholderText("Nombre visible")
        self.prompt_base_label_input.setMinimumWidth(200)
        prompt_base_row_one.addWidget(self.prompt_base_label_input)

        prompt_base_row_one.addWidget(QLabel("Ratios:"))
        self.prompt_base_ratios_input = QLineEdit()
        self.prompt_base_ratios_input.setPlaceholderText("1:1, 3:4, 9:16")
        self.prompt_base_ratios_input.setMinimumWidth(140)
        prompt_base_row_one.addWidget(self.prompt_base_ratios_input)

        self.prompt_base_enabled_checkbox = QCheckBox("Habilitado")
        self.prompt_base_enabled_checkbox.setChecked(True)
        prompt_base_row_one.addWidget(self.prompt_base_enabled_checkbox)
        prompt_base_row_one.addStretch(1)

        prompt_base_layout.addLayout(prompt_base_row_one)

        prompt_base_row_iter = QHBoxLayout()
        prompt_base_row_iter.addWidget(QLabel("Iteraciones (grupos):"))
        self.prompt_base_iterations_input = QLineEdit()
        self.prompt_base_iterations_input.setPlaceholderText(
            "outfit, pose, lighting, background, camera, mood, identity"
        )
        self.prompt_base_iterations_input.setMinimumWidth(260)
        prompt_base_row_iter.addWidget(self.prompt_base_iterations_input)
        prompt_base_row_iter.addStretch(1)
        prompt_base_layout.addLayout(prompt_base_row_iter)

        prompt_base_row_two = QHBoxLayout()
        prompt_base_row_two.addWidget(QLabel("Prompt base:"))
        prompt_base_layout.addLayout(prompt_base_row_two)

        self.prompt_base_text = QPlainTextEdit()
        self.prompt_base_text.setPlaceholderText("Describe el prompt base de la categoría o personaje.")
        self.prompt_base_text.setMinimumHeight(160)
        prompt_base_layout.addWidget(self.prompt_base_text)

        prompt_base_row_three = QHBoxLayout()
        self.prompt_base_save_btn = QPushButton("Guardar prompt base")
        self.prompt_base_new_btn = QPushButton("Nuevo")
        prompt_base_row_three.addWidget(self.prompt_base_save_btn)
        prompt_base_row_three.addWidget(self.prompt_base_new_btn)
        prompt_base_row_three.addStretch(1)
        prompt_base_layout.addLayout(prompt_base_row_three)

        layout.addWidget(prompt_base_group)
        layout.addStretch(1)

        self.prompt_base_save_btn.clicked.connect(self.save_prompt_base)
        self.prompt_base_new_btn.clicked.connect(self.reset_prompt_base_form)
        self.prompt_base_combo.currentIndexChanged.connect(self.load_prompt_base_from_combo)

        self._refresh_prompt_base_list()
        self.reset_prompt_base_form()

    def _refresh_prompt_base_list(self) -> None:
        self.prompt_base_combo.blockSignals(True)
        self.prompt_base_combo.clear()
        self.prompt_base_combo.addItem("Nuevo...", None)
        store = get_store()
        rows = store.list_prompt_bases(include_disabled=True)
        self.prompt_base_map = {row.key: row for row in rows}
        for row in rows:
            kind_label = "Personaje" if row.kind == "character" else "Categoría"
            label = f"{row.label} [{kind_label}]"
            self.prompt_base_combo.addItem(label, row.key)
        self.prompt_base_combo.blockSignals(False)

    def reset_prompt_base_form(self) -> None:
        self.prompt_base_combo.setCurrentIndex(0)
        self.prompt_base_kind_combo.setCurrentIndex(0)
        self.prompt_base_key_input.clear()
        self.prompt_base_key_input.setEnabled(True)
        self.prompt_base_label_input.clear()
        self.prompt_base_ratios_input.clear()
        self.prompt_base_enabled_checkbox.setChecked(True)
        self.prompt_base_iterations_input.clear()
        self.prompt_base_text.clear()

    def load_prompt_base_from_combo(self) -> None:
        key = self.prompt_base_combo.currentData()
        if not key:
            self.prompt_base_key_input.setEnabled(True)
            return
        row = self.prompt_base_map.get(str(key))
        if not row:
            return
        kind_idx = self.prompt_base_kind_combo.findData(row.kind)
        if kind_idx >= 0:
            self.prompt_base_kind_combo.setCurrentIndex(kind_idx)
        self.prompt_base_key_input.setText(row.key)
        self.prompt_base_key_input.setEnabled(False)
        self.prompt_base_label_input.setText(row.label)
        self.prompt_base_ratios_input.setText(", ".join(row.allowed_ratios))
        self.prompt_base_enabled_checkbox.setChecked(row.enabled)
        self.prompt_base_iterations_input.setText(", ".join(row.iteration_groups))
        self.prompt_base_text.setPlainText(row.base_prompt)

    def save_prompt_base(self) -> None:
        key = self.prompt_base_key_input.text().strip()
        label = self.prompt_base_label_input.text().strip()
        base_prompt = self.prompt_base_text.toPlainText().strip()
        kind = str(self.prompt_base_kind_combo.currentData() or "category")
        ratios_raw = self.prompt_base_ratios_input.text().strip()
        iterations_raw = self.prompt_base_iterations_input.text().strip()
        enabled = self.prompt_base_enabled_checkbox.isChecked()

        if not key:
            QMessageBox.warning(self, "Prompts base", "La key es obligatoria.")
            return
        if not label:
            QMessageBox.warning(self, "Prompts base", "El label es obligatorio.")
            return
        if not base_prompt:
            QMessageBox.warning(self, "Prompts base", "El prompt base no puede estar vacío.")
            return

        allowed_ratios = [r.strip() for r in ratios_raw.split(",") if r.strip()]
        iteration_groups = [g.strip() for g in iterations_raw.split(",") if g.strip()]
        store = get_store()
        store.upsert_prompt_base(
            key=key,
            label=label,
            base_prompt=base_prompt,
            kind=kind,
            allowed_ratios=allowed_ratios,
            iteration_groups=iteration_groups,
            enabled=enabled,
        )

        self._refresh_prompt_base_list()
        idx = self.prompt_base_combo.findData(key)
        if idx >= 0:
            self.prompt_base_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "Prompts base", "Prompt base guardado.")
        self.catalog_updated.emit()
