from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.config.bulk_images_prompts import (
    BulkImagePrompt,
    bulk_image_prompts_example_payload,
    delete_bulk_image_prompt,
    import_bulk_image_prompts,
    load_bulk_image_prompts,
    save_bulk_image_prompt,
)


class BulkImagesPromptWindow(QMainWindow):
    """Prompt library for the Bulk Images workflow."""

    send_listed_requested = Signal(list, int)

    COLUMNS = [
        ("id", "ID"),
        ("title", "Título"),
        ("category", "Categoría"),
        ("subcategory", "Subcategoría"),
        ("collection", "Colección"),
        ("subject", "Sujeto"),
        ("style", "Estilo"),
        ("mood", "Mood"),
        ("environment", "Entorno"),
        ("lighting", "Iluminación"),
        ("camera", "Cámara"),
        ("composition", "Composición"),
        ("color_palette", "Paleta"),
        ("ratio", "Ratio"),
        ("model_hint", "Modelo"),
        ("workflow_hint", "Workflow"),
        ("tags", "Tags"),
        ("quantity", "Cantidad"),
        ("priority", "Prioridad"),
        ("status", "Estado"),
        ("enabled", "Activo"),
        ("positive_prompt", "Prompt positivo"),
        ("negative_prompt", "Prompt negativo"),
        ("notes", "Notas"),
    ]

    FILTERS = [
        ("category", "Categoría"),
        ("subcategory", "Subcategoría"),
        ("collection", "Colección"),
        ("subject", "Sujeto"),
        ("style", "Estilo"),
        ("mood", "Mood"),
        ("ratio", "Ratio"),
        ("model_hint", "Modelo"),
        ("workflow_hint", "Workflow"),
        ("status", "Estado"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bulk Images — Biblioteca de prompts")
        self.resize(1400, 720)
        self.prompts: list[BulkImagePrompt] = []
        self.visible_prompts: list[BulkImagePrompt] = []
        self.filter_combos: dict[str, QComboBox] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        title = QLabel("Bulk Images — prompts únicos para creación masiva")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Biblioteca inicial sin combinaciones: cada fila representa un prompt final con metadatos "
            "para filtrar por categoría, subcategoría, estilo, ratio, workflow y estado."
        )
        subtitle.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(subtitle)

        filters_group = QGroupBox("Filtros de biblioteca")
        filters_layout = QGridLayout(filters_group)
        for index, (field_name, label) in enumerate(self.FILTERS):
            row = index // 5
            col = (index % 5) * 2
            filters_layout.addWidget(QLabel(f"{label}:"), row, col)
            combo = QComboBox()
            combo.setMinimumWidth(150)
            combo.currentIndexChanged.connect(self.apply_filters)
            self.filter_combos[field_name] = combo
            filters_layout.addWidget(combo, row, col + 1)

        filters_layout.addWidget(QLabel("Buscar:"), 2, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ID, título, prompt, tags, notas...")
        self.search_input.textChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.search_input, 2, 1, 1, 5)

        self.enabled_combo = QComboBox()
        self.enabled_combo.addItem("Todos", None)
        self.enabled_combo.addItem("Activos", True)
        self.enabled_combo.addItem("Inactivos", False)
        self.enabled_combo.currentIndexChanged.connect(self.apply_filters)
        filters_layout.addWidget(QLabel("Activo:"), 2, 6)
        filters_layout.addWidget(self.enabled_combo, 2, 7)

        self.reset_btn = QPushButton("Restablecer filtros")
        self.reset_btn.clicked.connect(self.reset_filters)
        filters_layout.addWidget(self.reset_btn, 2, 8, 1, 2)
        layout.addWidget(filters_group)

        summary_row = QHBoxLayout()
        self.summary_label = QLabel("0 prompts")
        summary_row.addWidget(self.summary_label)
        summary_row.addStretch(1)

        summary_row.addWidget(QLabel("Imágenes por prompt:"))
        self.quantity_per_prompt_spin = QSpinBox()
        self.quantity_per_prompt_spin.setRange(1, 999)
        self.quantity_per_prompt_spin.setValue(1)
        self.quantity_per_prompt_spin.setToolTip(
            "Cantidad de imágenes que se crearán por cada prompt listado al enviarlos a la cola."
        )
        self.quantity_per_prompt_spin.valueChanged.connect(self.apply_filters)
        summary_row.addWidget(self.quantity_per_prompt_spin)
        self.save_selected_btn = QPushButton("Guardar fila seleccionada")
        self.save_selected_btn.setToolTip("Guarda en base de datos los cambios editados en la fila seleccionada.")
        self.save_selected_btn.clicked.connect(self.save_selected_prompt)
        summary_row.addWidget(self.save_selected_btn)

        self.delete_selected_btn = QPushButton("Eliminar seleccionado")
        self.delete_selected_btn.setToolTip("Borra de base de datos el prompt Bulk Images seleccionado.")
        self.delete_selected_btn.clicked.connect(self.delete_selected_prompt)
        summary_row.addWidget(self.delete_selected_btn)

        self.import_json_btn = QPushButton("Importar prompts desde JSON")
        self.import_json_btn.setToolTip("Importa prompts en bloque desde un archivo JSON y actualiza la biblioteca local.")
        self.import_json_btn.clicked.connect(self.import_prompts_from_json)
        summary_row.addWidget(self.import_json_btn)

        self.example_json_btn = QPushButton("Guardar JSON ejemplo")
        self.example_json_btn.setToolTip("Guarda un archivo JSON de ejemplo con la estructura esperada para importación masiva.")
        self.example_json_btn.clicked.connect(self.save_example_json)
        summary_row.addWidget(self.example_json_btn)

        self.send_listed_btn = QPushButton("Enviar prompts listados a la cola")
        self.send_listed_btn.setToolTip("Encola todos los prompts activos que se muestran con los filtros actuales.")
        self.send_listed_btn.clicked.connect(self.request_send_listed_prompts)
        summary_row.addWidget(self.send_listed_btn)
        layout.addLayout(summary_row)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _, label in self.COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemSelectionChanged.connect(self._update_selection_actions)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        layout.addWidget(self.table, 1)

        self.reload()
        self._update_selection_actions()

    def reload(self) -> None:
        self.prompts = load_bulk_image_prompts()
        self._populate_filter_options()
        self.apply_filters()

    def reset_filters(self) -> None:
        for combo in self.filter_combos.values():
            combo.setCurrentIndex(0)
        self.enabled_combo.setCurrentIndex(0)
        self.search_input.clear()
        self.apply_filters()

    def _populate_filter_options(self) -> None:
        for field_name, combo in self.filter_combos.items():
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Todos", None)
            values = sorted({str(getattr(prompt, field_name)) for prompt in self.prompts if getattr(prompt, field_name)})
            for value in values:
                combo.addItem(value, value)
            index = combo.findData(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def apply_filters(self) -> None:
        rows = self.prompts
        for field_name, combo in self.filter_combos.items():
            selected = combo.currentData()
            if selected is not None:
                rows = [prompt for prompt in rows if getattr(prompt, field_name) == selected]

        enabled = self.enabled_combo.currentData()
        if enabled is not None:
            rows = [prompt for prompt in rows if prompt.enabled is enabled]

        query = self.search_input.text().strip().lower()
        if query:
            rows = [prompt for prompt in rows if query in self._search_blob(prompt)]

        self.visible_prompts = list(rows)
        quantity_per_prompt = self.quantity_per_prompt_spin.value()
        active_count = sum(quantity_per_prompt for prompt in rows if prompt.enabled and prompt.positive_prompt.strip())
        self._populate_table(rows)
        self.summary_label.setText(f"{len(rows)} de {len(self.prompts)} prompts ({active_count} imágenes enviables)")
        self.send_listed_btn.setEnabled(active_count > 0)

    def _update_selection_actions(self) -> None:
        has_selection = bool(self.table.selectionModel() and self.table.selectionModel().selectedRows())
        self.save_selected_btn.setEnabled(has_selection)
        self.delete_selected_btn.setEnabled(has_selection)

    def _selected_row_index(self) -> int | None:
        selected = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not selected:
            return None
        return int(selected[0].row())

    def _prompt_from_table_row(self, row_index: int) -> BulkImagePrompt:
        values: dict[str, object] = {}
        for col_index, (field_name, _) in enumerate(self.COLUMNS):
            item = self.table.item(row_index, col_index)
            text = item.text().strip() if item else ""
            if field_name == "tags":
                values[field_name] = [tag.strip() for tag in text.split(",") if tag.strip()]
            elif field_name in {"quantity", "priority"}:
                values[field_name] = int(text or (1 if field_name == "quantity" else 100))
            elif field_name == "enabled":
                values[field_name] = text.lower() in {"sí", "si", "true", "1", "yes", "activo"}
            else:
                values[field_name] = text
        return BulkImagePrompt.from_dict(values)

    def save_selected_prompt(self) -> None:
        row_index = self._selected_row_index()
        if row_index is None:
            return
        try:
            prompt = self._prompt_from_table_row(row_index)
            save_bulk_image_prompt(prompt)
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Bulk Images", f"No se pudo guardar el prompt:\n{exc}")
            return
        self.reload()
        QMessageBox.information(self, "Bulk Images", "Prompt guardado en base de datos.")

    def delete_selected_prompt(self) -> None:
        row_index = self._selected_row_index()
        if row_index is None:
            return
        id_item = self.table.item(row_index, 0)
        prompt_id = id_item.text().strip() if id_item else ""
        if not prompt_id:
            return
        confirm = QMessageBox.question(
            self,
            "Eliminar prompt Bulk Images",
            f"¿Quieres eliminar el prompt '{prompt_id}' de la base de datos?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        delete_bulk_image_prompt(prompt_id)
        self.reload()
        QMessageBox.information(self, "Bulk Images", "Prompt eliminado.")

    def import_prompts_from_json(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Importar prompts Bulk Images",
            "",
            "JSON (*.json);;Todos los archivos (*)",
        )
        if not file_name:
            return
        try:
            added, updated = import_bulk_image_prompts(Path(file_name))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Importar prompts", f"No se pudo importar el JSON:\n{exc}")
            return

        self.reload()
        QMessageBox.information(
            self,
            "Importar prompts",
            f"Importación completada. Añadidos: {added}. Actualizados: {updated}.",
        )

    def save_example_json(self) -> None:
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar JSON ejemplo",
            "bulk_images_prompts_example.json",
            "JSON (*.json);;Todos los archivos (*)",
        )
        if not file_name:
            return
        try:
            with open(file_name, "w", encoding="utf-8") as fh:
                json.dump(bulk_image_prompts_example_payload(), fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        except OSError as exc:
            QMessageBox.critical(self, "JSON ejemplo", f"No se pudo guardar el ejemplo:\n{exc}")
            return
        QMessageBox.information(self, "JSON ejemplo", f"Ejemplo guardado en:\n{file_name}")

    def request_send_listed_prompts(self) -> None:
        prompts = [prompt for prompt in self.visible_prompts if prompt.enabled and prompt.positive_prompt.strip()]
        if prompts:
            self.send_listed_requested.emit(prompts, self.quantity_per_prompt_spin.value())

    def _populate_table(self, prompts: list[BulkImagePrompt]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(prompts))
        for row_index, prompt in enumerate(prompts):
            for col_index, (field_name, _) in enumerate(self.COLUMNS):
                value = getattr(prompt, field_name)
                if isinstance(value, list):
                    display = ", ".join(value)
                elif isinstance(value, bool):
                    display = "Sí" if value else "No"
                else:
                    display = str(value)
                item = QTableWidgetItem(display)
                item.setToolTip(display)
                if field_name in {"priority", "quantity"}:
                    item.setData(Qt.EditRole, int(value))
                self.table.setItem(row_index, col_index, item)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)

    def _search_blob(self, prompt: BulkImagePrompt) -> str:
        parts = []
        for field_name, _ in self.COLUMNS:
            value = getattr(prompt, field_name)
            parts.extend(value if isinstance(value, list) else [str(value)])
        return " ".join(parts).lower()
