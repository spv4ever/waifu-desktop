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
    QCheckBox,
    QLabel,
    QMessageBox,
    QGroupBox,
    QSpinBox,
)

from app.data.repositories import PromptVariationRow
from app.data.storage import get_store


class PromptVariationWindow(QMainWindow):
    catalog_updated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mantenimiento de opciones y variaciones")
        self.resize(760, 360)

        self.store = get_store()
        self._value_map: dict[str, PromptVariationRow] = {}
        self._selected_value_original: str | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        group_box = QGroupBox("Grupos y valores")
        group_layout = QVBoxLayout(group_box)

        group_row = QHBoxLayout()
        group_row.addWidget(QLabel("Grupo:"))
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(240)
        group_row.addWidget(self.group_combo)
        group_row.addWidget(QLabel("Clave grupo:"))
        self.group_key_input = QLineEdit()
        self.group_key_input.setPlaceholderText("ej: wardrobe.tops")
        self.group_key_input.setMinimumWidth(220)
        group_row.addWidget(self.group_key_input)
        group_row.addStretch(1)
        group_layout.addLayout(group_row)

        value_row = QHBoxLayout()
        value_row.addWidget(QLabel("Valor:"))
        self.value_combo = QComboBox()
        self.value_combo.setMinimumWidth(240)
        value_row.addWidget(self.value_combo)
        value_row.addWidget(QLabel("Texto:"))
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Nombre de la opción")
        self.value_input.setMinimumWidth(220)
        value_row.addWidget(self.value_input)
        value_row.addStretch(1)
        group_layout.addLayout(value_row)

        details_row = QHBoxLayout()
        details_row.addWidget(QLabel("Posición:"))
        self.position_spin = QSpinBox()
        self.position_spin.setRange(0, 10000)
        details_row.addWidget(self.position_spin)
        self.enabled_checkbox = QCheckBox("Habilitado")
        self.enabled_checkbox.setChecked(True)
        details_row.addWidget(self.enabled_checkbox)
        details_row.addStretch(1)
        group_layout.addLayout(details_row)

        action_row = QHBoxLayout()
        self.save_btn = QPushButton("Guardar")
        self.new_btn = QPushButton("Nuevo")
        self.disable_btn = QPushButton("Deshabilitar")
        action_row.addWidget(self.save_btn)
        action_row.addWidget(self.new_btn)
        action_row.addWidget(self.disable_btn)
        action_row.addStretch(1)
        group_layout.addLayout(action_row)

        layout.addWidget(group_box)
        layout.addStretch(1)

        self.group_combo.currentIndexChanged.connect(self._on_group_changed)
        self.value_combo.currentIndexChanged.connect(self._on_value_changed)
        self.save_btn.clicked.connect(self.save_variation)
        self.new_btn.clicked.connect(self.reset_form)
        self.disable_btn.clicked.connect(self.disable_variation)

        self._refresh_group_list()
        self.reset_form()

    def _refresh_group_list(self) -> None:
        current_data = self.group_combo.currentData()
        groups = self.store.list_prompt_variation_groups(include_disabled=True)
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("Nuevo...", None)
        for group in groups:
            self.group_combo.addItem(group, group)
        if current_data:
            idx = self.group_combo.findData(current_data)
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)
        self.group_combo.blockSignals(False)

    def _refresh_value_list(self) -> None:
        group_key = self._current_group_key()
        current_data = self.value_combo.currentData()
        self.value_combo.blockSignals(True)
        self.value_combo.clear()
        self.value_combo.addItem("Nuevo...", None)
        self._value_map = {}
        if group_key:
            rows = self.store.list_prompt_variation_rows(group_key=group_key, include_disabled=True)
            for row in rows:
                label = row.value
                if not row.enabled:
                    label = f"{label} (deshabilitado)"
                self.value_combo.addItem(label, row.value)
                self._value_map[row.value] = row
        if current_data:
            idx = self.value_combo.findData(current_data)
            if idx >= 0:
                self.value_combo.setCurrentIndex(idx)
        self.value_combo.blockSignals(False)

    def _current_group_key(self) -> str:
        group_data = self.group_combo.currentData()
        if isinstance(group_data, str) and group_data.strip():
            return group_data.strip()
        return self.group_key_input.text().strip()

    def _on_group_changed(self) -> None:
        group_data = self.group_combo.currentData()
        if group_data:
            self.group_key_input.setText(str(group_data))
            self.group_key_input.setEnabled(False)
        else:
            self.group_key_input.clear()
            self.group_key_input.setEnabled(True)
        self._refresh_value_list()
        self._reset_value_fields()

    def _on_value_changed(self) -> None:
        value_data = self.value_combo.currentData()
        if not value_data:
            self._reset_value_fields()
            return
        row = self._value_map.get(str(value_data))
        if not row:
            self._reset_value_fields()
            return
        self._selected_value_original = row.value
        self.value_input.setText(row.value)
        self.position_spin.setValue(row.position)
        self.enabled_checkbox.setChecked(row.enabled)

    def _next_position(self) -> int:
        if not self._value_map:
            return 0
        return max(row.position for row in self._value_map.values()) + 1

    def _reset_value_fields(self) -> None:
        self._selected_value_original = None
        self.value_input.clear()
        self.position_spin.setValue(self._next_position())
        self.enabled_checkbox.setChecked(True)

    def reset_form(self) -> None:
        self.group_combo.setCurrentIndex(0)
        self.group_key_input.clear()
        self.group_key_input.setEnabled(True)
        self._refresh_value_list()
        self._reset_value_fields()

    def save_variation(self) -> None:
        group_key = self._current_group_key()
        value = self.value_input.text().strip()
        position = int(self.position_spin.value())
        enabled = self.enabled_checkbox.isChecked()

        if not group_key:
            QMessageBox.warning(self, "Variaciones", "La clave del grupo es obligatoria.")
            return
        if not value:
            QMessageBox.warning(self, "Variaciones", "El valor de la opción es obligatorio.")
            return

        original_value = self._selected_value_original
        if original_value and original_value != value:
            original_row = self._value_map.get(original_value)
            if original_row:
                self.store.upsert_prompt_variation(
                    group_key=group_key,
                    value=original_row.value,
                    position=original_row.position,
                    enabled=False,
                )

        self.store.upsert_prompt_variation(
            group_key=group_key,
            value=value,
            position=position,
            enabled=enabled,
        )

        self._refresh_group_list()
        idx = self.group_combo.findData(group_key)
        if idx >= 0:
            self.group_combo.setCurrentIndex(idx)
        self._refresh_value_list()
        value_idx = self.value_combo.findData(value)
        if value_idx >= 0:
            self.value_combo.setCurrentIndex(value_idx)

        QMessageBox.information(self, "Variaciones", "Variación guardada.")
        self.catalog_updated.emit()

    def disable_variation(self) -> None:
        group_key = self._current_group_key()
        value_data = self.value_combo.currentData()
        if not group_key or not value_data:
            QMessageBox.warning(self, "Variaciones", "Selecciona una variación para deshabilitar.")
            return
        row = self._value_map.get(str(value_data))
        if not row:
            QMessageBox.warning(self, "Variaciones", "No se encontró la variación seleccionada.")
            return

        confirm = QMessageBox.question(
            self,
            "Deshabilitar",
            f"¿Quieres deshabilitar la opción '{row.value}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.store.upsert_prompt_variation(
            group_key=group_key,
            value=row.value,
            position=row.position,
            enabled=False,
        )
        self._refresh_value_list()
        self._reset_value_fields()
        QMessageBox.information(self, "Variaciones", "Variación deshabilitada.")
        self.catalog_updated.emit()
