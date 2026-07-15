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
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.config.bulk_images_prompts import (
    BulkImagePrompt,
    bulk_image_prompts_example_payload,
    import_bulk_image_prompts,
    load_bulk_image_prompts,
)


class BulkImagesPromptWindow(QMainWindow):
    """Prompt library for the Bulk Images workflow."""

    send_listed_requested = Signal(list)

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
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        layout.addWidget(self.table, 1)

        self.reload()

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
        active_count = sum(1 for prompt in rows if prompt.enabled and prompt.positive_prompt.strip())
        self._populate_table(rows)
        self.summary_label.setText(f"{len(rows)} de {len(self.prompts)} prompts ({active_count} activos enviables)")
        self.send_listed_btn.setEnabled(active_count > 0)

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
            self.send_listed_requested.emit(prompts)

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
                if field_name == "priority":
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
