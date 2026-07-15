from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from app.data.repositories import DollimagePromptRow
from app.data.storage import get_store


class DollimagesPromptWindow(QMainWindow):
    catalog_updated = Signal()
    generate_selected_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mantenimiento de prompts Dollimages")
        self.resize(760, 420)

        self.store = get_store()
        self._prompt_map: dict[int, DollimagePromptRow] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        prompt_group = QGroupBox("Prompts Dollimages")
        prompt_layout = QVBoxLayout(prompt_group)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Prompt existente:"))
        self.prompt_combo = QComboBox()
        self.prompt_combo.setMinimumWidth(320)
        select_row.addWidget(self.prompt_combo)
        select_row.addWidget(QLabel("ID:"))
        self.prompt_id_label = QLabel("—")
        select_row.addWidget(self.prompt_id_label)
        self.prompt_enabled_checkbox = QCheckBox("Habilitado")
        self.prompt_enabled_checkbox.setChecked(True)
        select_row.addWidget(self.prompt_enabled_checkbox)
        select_row.addStretch(1)
        prompt_layout.addLayout(select_row)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Grupo:"))
        self.prompt_group_input = QLineEdit()
        self.prompt_group_input.setPlaceholderText("Ej: enfermeras")
        title_row.addWidget(self.prompt_group_input)
        title_row.addWidget(QLabel("Título:"))
        self.prompt_title_input = QLineEdit()
        self.prompt_title_input.setPlaceholderText("Título visible del prompt")
        title_row.addWidget(self.prompt_title_input)
        title_row.addWidget(QLabel("Tipología:"))
        self.prompt_typology_combo = QComboBox()
        self.prompt_typology_combo.addItem("Normal", "normal")
        self.prompt_typology_combo.addItem("SFW", "sfw")
        self.prompt_typology_combo.addItem("NSFW", "nsfw")
        title_row.addWidget(self.prompt_typology_combo)
        title_row.addStretch(1)
        prompt_layout.addLayout(title_row)

        text_row = QHBoxLayout()
        text_row.addWidget(QLabel("Prompt:"))
        prompt_layout.addLayout(text_row)
        self.prompt_text_input = QPlainTextEdit()
        self.prompt_text_input.setPlaceholderText("Texto base del prompt para Dollimages.")
        self.prompt_text_input.setMinimumHeight(160)
        prompt_layout.addWidget(self.prompt_text_input)

        action_row = QHBoxLayout()
        self.save_btn = QPushButton("Guardar")
        self.new_btn = QPushButton("Nuevo")
        self.delete_btn = QPushButton("Eliminar")
        self.import_btn = QPushButton("Importar JSON Dollimages")
        self.generate_selected_btn = QPushButton("Generar prompt seleccionado")
        action_row.addWidget(self.save_btn)
        action_row.addWidget(self.new_btn)
        action_row.addWidget(self.delete_btn)
        action_row.addWidget(self.import_btn)
        action_row.addWidget(self.generate_selected_btn)
        action_row.addStretch(1)
        prompt_layout.addLayout(action_row)

        layout.addWidget(prompt_group)
        layout.addStretch(1)

        self.prompt_combo.currentIndexChanged.connect(self.load_prompt_from_combo)
        self.save_btn.clicked.connect(self.save_prompt)
        self.new_btn.clicked.connect(self.reset_form)
        self.delete_btn.clicked.connect(self.delete_prompt)
        self.import_btn.clicked.connect(self.import_prompts)
        self.generate_selected_btn.clicked.connect(self.request_generate_selected_prompt)

        self._refresh_prompt_list()
        self.reset_form()

    def _refresh_prompt_list(self) -> None:
        current_id = self.prompt_combo.currentData()
        rows = self.store.list_dollimage_prompts(include_disabled=True)
        self._prompt_map = {row.id: row for row in rows}
        self.prompt_combo.blockSignals(True)
        self.prompt_combo.clear()
        self.prompt_combo.addItem("Nuevo...", None)
        for row in rows:
            group_label = row.group_name or "Sin grupo"
            label = f"{group_label} - {row.title} [{row.typology}]"
            if not row.enabled:
                label = f"{label} (deshabilitado)"
            self.prompt_combo.addItem(label, row.id)
        if current_id:
            idx = self.prompt_combo.findData(current_id)
            if idx >= 0:
                self.prompt_combo.setCurrentIndex(idx)
        self.prompt_combo.blockSignals(False)

    def reset_form(self) -> None:
        self.prompt_combo.setCurrentIndex(0)
        self.prompt_id_label.setText("—")
        self.prompt_title_input.clear()
        self.prompt_group_input.clear()
        self.prompt_text_input.clear()
        self.prompt_typology_combo.setCurrentIndex(0)
        self.prompt_enabled_checkbox.setChecked(True)

    def request_generate_selected_prompt(self) -> None:
        prompt_id = self.prompt_combo.currentData()
        if not prompt_id:
            QMessageBox.warning(
                self,
                "Dollimages",
                "Selecciona un prompt existente para generarlo.",
            )
            return
        row = self._prompt_map.get(int(prompt_id))
        if not row:
            QMessageBox.warning(
                self,
                "Dollimages",
                "No se encontró el prompt seleccionado.",
            )
            return
        self.generate_selected_requested.emit(row)

    def load_prompt_from_combo(self) -> None:
        prompt_id = self.prompt_combo.currentData()
        if not prompt_id:
            self.reset_form()
            return
        row = self._prompt_map.get(int(prompt_id))
        if not row:
            return
        self.prompt_id_label.setText(str(row.id))
        self.prompt_title_input.setText(row.title)
        self.prompt_group_input.setText(row.group_name)
        self.prompt_text_input.setPlainText(row.prompt_text)
        idx = self.prompt_typology_combo.findData(row.typology)
        if idx >= 0:
            self.prompt_typology_combo.setCurrentIndex(idx)
        self.prompt_enabled_checkbox.setChecked(row.enabled)

    def save_prompt(self) -> None:
        prompt_id = self.prompt_combo.currentData()
        group_name = self.prompt_group_input.text().strip()
        title = self.prompt_title_input.text().strip()
        prompt_text = self.prompt_text_input.toPlainText().strip()
        typology = str(self.prompt_typology_combo.currentData() or "normal")
        enabled = self.prompt_enabled_checkbox.isChecked()

        if not title:
            QMessageBox.warning(self, "Dollimages", "El título es obligatorio.")
            return
        if not prompt_text:
            QMessageBox.warning(self, "Dollimages", "El prompt no puede estar vacío.")
            return

        saved_id = self.store.save_dollimage_prompt(
            prompt_id=int(prompt_id) if prompt_id else None,
            group_name=group_name,
            title=title,
            prompt_text=prompt_text,
            typology=typology,
            enabled=enabled,
        )

        self._refresh_prompt_list()
        idx = self.prompt_combo.findData(saved_id)
        if idx >= 0:
            self.prompt_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "Dollimages", "Prompt guardado.")
        self.catalog_updated.emit()

    def delete_prompt(self) -> None:
        prompt_id = self.prompt_combo.currentData()
        if not prompt_id:
            QMessageBox.warning(self, "Dollimages", "Selecciona un prompt para eliminar.")
            return
        row = self._prompt_map.get(int(prompt_id))
        label = row.title if row else f"Prompt #{prompt_id}"
        confirm = QMessageBox.question(
            self,
            "Eliminar",
            f"¿Quieres eliminar este prompt?\n\n{label}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.store.delete_dollimage_prompt(prompt_id=int(prompt_id))
        self._refresh_prompt_list()
        self.reset_form()
        QMessageBox.information(self, "Dollimages", "Prompt eliminado.")
        self.catalog_updated.emit()

    def import_prompts(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar prompts Dollimages",
            "",
            "Catálogo JSON (*.json);;Todos los archivos (*.*)",
        )
        if not file_path:
            return

        try:
            raw_text = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Importar prompts Dollimages", f"No se pudo leer el fichero.\n{exc}")
            return

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(
                self,
                "Importar prompts Dollimages",
                f"El fichero no contiene JSON válido.\n{exc}",
            )
            return

        prompts: list[dict[str, object]] = []
        if isinstance(data, dict):
            raw_prompts = data.get("prompts")
            if isinstance(raw_prompts, list):
                prompts = [item for item in raw_prompts if isinstance(item, dict)]
        elif isinstance(data, list):
            prompts = [item for item in data if isinstance(item, dict)]

        if not prompts:
            QMessageBox.warning(
                self,
                "Importar prompts Dollimages",
                "No se encontraron prompts en el JSON. Se esperaba una lista en 'prompts'.",
            )
            return

        imported = self.store.import_dollimage_prompts(prompts)
        if imported == 0:
            QMessageBox.warning(
                self,
                "Importar prompts Dollimages",
                "No se pudieron importar prompts válidos.",
            )
            return

        self._refresh_prompt_list()
        self.reset_form()
        QMessageBox.information(
            self,
            "Importar prompts Dollimages",
            f"Importación completada.\nPrompts importados: {imported}",
        )
        self.catalog_updated.emit()
