from __future__ import annotations

import json
from pathlib import Path

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
    QListWidget,
    QListWidgetItem,
    QFileDialog,
)

from app.data.repositories import PromptBaseRow
from app.data.storage import get_store


class PromptBaseWindow(QMainWindow):
    catalog_updated = Signal()

    ITERATION_GROUP_OPTIONS = [
        ("identity", "Identidad"),
        ("outfit", "Outfit"),
        ("pose", "Pose"),
        ("background", "Fondo"),
        ("lighting", "Iluminación"),
        ("camera", "Cámara"),
        ("mood", "Mood"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mantenimiento de categorías y personajes")
        self.resize(780, 520)

        self.store = get_store()
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
        self.prompt_base_iterations_list = QListWidget()
        self.prompt_base_iterations_list.setMinimumWidth(260)
        self.prompt_base_iterations_list.setMinimumHeight(90)
        self.prompt_base_iterations_list.setToolTip(
            "Selecciona los grupos de iteración disponibles."
        )
        self._build_iteration_group_list()
        prompt_base_row_iter.addWidget(self.prompt_base_iterations_list)
        prompt_base_row_iter.addStretch(1)
        prompt_base_layout.addLayout(prompt_base_row_iter)

        prompt_base_row_iter_add = QHBoxLayout()
        prompt_base_row_iter_add.addWidget(QLabel("Añadir grupo:"))
        self.prompt_base_group_combo = QComboBox()
        self.prompt_base_group_combo.setMinimumWidth(220)
        self.prompt_base_group_combo.setToolTip(
            "Elige un grupo existente o escribe uno personalizado."
        )
        prompt_base_row_iter_add.addWidget(self.prompt_base_group_combo)
        self.prompt_base_group_input = QLineEdit()
        self.prompt_base_group_input.setPlaceholderText("ej: characters.makima.g1")
        self.prompt_base_group_input.setMinimumWidth(220)
        prompt_base_row_iter_add.addWidget(self.prompt_base_group_input)
        self.prompt_base_group_add_btn = QPushButton("Añadir")
        prompt_base_row_iter_add.addWidget(self.prompt_base_group_add_btn)
        prompt_base_row_iter_add.addStretch(1)
        prompt_base_layout.addLayout(prompt_base_row_iter_add)

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
        self.prompt_base_import_btn = QPushButton("Importar JSON Dollimages")
        prompt_base_row_three.addWidget(self.prompt_base_save_btn)
        prompt_base_row_three.addWidget(self.prompt_base_new_btn)
        prompt_base_row_three.addWidget(self.prompt_base_import_btn)
        prompt_base_row_three.addStretch(1)
        prompt_base_layout.addLayout(prompt_base_row_three)

        layout.addWidget(prompt_base_group)
        layout.addStretch(1)

        self.prompt_base_save_btn.clicked.connect(self.save_prompt_base)
        self.prompt_base_new_btn.clicked.connect(self.reset_prompt_base_form)
        self.prompt_base_import_btn.clicked.connect(self.import_prompt_catalog)
        self.prompt_base_combo.currentIndexChanged.connect(self.load_prompt_base_from_combo)
        self.prompt_base_group_add_btn.clicked.connect(self.add_iteration_group)

        self._refresh_prompt_base_list()
        self._refresh_iteration_group_choices()
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
        self._set_checked_iteration_groups([])
        self.prompt_base_text.clear()
        self.prompt_base_group_combo.setCurrentIndex(0)
        self.prompt_base_group_input.clear()

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
        self._set_checked_iteration_groups(row.iteration_groups)
        self.prompt_base_text.setPlainText(row.base_prompt)

    def save_prompt_base(self) -> None:
        key = self.prompt_base_key_input.text().strip()
        label = self.prompt_base_label_input.text().strip()
        base_prompt = self.prompt_base_text.toPlainText().strip()
        kind = str(self.prompt_base_kind_combo.currentData() or "category")
        ratios_raw = self.prompt_base_ratios_input.text().strip()
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
        iteration_groups = self._checked_iteration_groups()
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

    def import_prompt_catalog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar catálogo Dollimages",
            "",
            "Catálogo JSON (*.json);;Todos los archivos (*.*)",
        )
        if not file_path:
            return

        try:
            raw_text = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Importar catálogo Dollimages", f"No se pudo leer el fichero.\n{exc}")
            return

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(
                self,
                "Importar catálogo Dollimages",
                f"El fichero no contiene JSON válido.\n{exc}",
            )
            return

        if not isinstance(data, dict):
            QMessageBox.warning(
                self, "Importar catálogo Dollimages", "El JSON debe tener un objeto raíz."
            )
            return

        errors: list[str] = []
        bases: list[dict[str, object]] = []

        def _collect_bases(source: object, *, default_kind: str) -> None:
            if source is None:
                return
            if not isinstance(source, dict):
                errors.append(f"Se esperaba un dict para '{default_kind}s'.")
                return
            for key, entry in source.items():
                if not isinstance(entry, dict):
                    errors.append(f"Entrada inválida en '{key}'.")
                    continue
                base_prompt = str(entry.get("base_prompt", "")).strip()
                if not base_prompt:
                    errors.append(f"'{key}' no tiene base_prompt.")
                    continue
                label = str(entry.get("label", key)).strip() or str(key)
                allowed_ratios = entry.get("allowed_ratios") or []
                if not isinstance(allowed_ratios, list):
                    errors.append(f"'{key}' tiene allowed_ratios inválido.")
                    allowed_ratios = []
                iteration_groups = entry.get("iteration_groups") or []
                if not isinstance(iteration_groups, list):
                    errors.append(f"'{key}' tiene iteration_groups inválido.")
                    iteration_groups = []
                kind = str(entry.get("kind") or default_kind)
                enabled = bool(entry.get("enabled", True))
                bases.append(
                    {
                        "key": str(key),
                        "label": label,
                        "base_prompt": base_prompt,
                        "kind": kind,
                        "allowed_ratios": [str(r).strip() for r in allowed_ratios if str(r).strip()],
                        "iteration_groups": [
                            str(group).strip()
                            for group in iteration_groups
                            if isinstance(group, (str, int, float)) and str(group).strip()
                        ],
                        "enabled": enabled,
                    }
                )

        _collect_bases(data.get("categories"), default_kind="category")
        _collect_bases(data.get("characters"), default_kind="character")

        if errors:
            message = "\n".join(errors[:10])
            if len(errors) > 10:
                message = f"{message}\n..."
            QMessageBox.warning(
                self, "Importar catálogo Dollimages", f"Errores detectados:\n{message}"
            )
            return

        store = get_store()
        imported_bases = 0
        for base in bases:
            store.upsert_prompt_base(
                key=str(base["key"]),
                label=str(base["label"]),
                base_prompt=str(base["base_prompt"]),
                kind=str(base["kind"]),
                allowed_ratios=list(base["allowed_ratios"]),
                iteration_groups=list(base["iteration_groups"]),
                enabled=bool(base["enabled"]),
            )
            imported_bases += 1

        imported_variations = store.import_prompt_variations(data)

        if imported_bases == 0 and imported_variations == 0:
            QMessageBox.warning(
                self,
                "Importar catálogo Dollimages",
                "No se encontraron categorías, personajes u opciones para importar.",
            )
            return

        self._refresh_prompt_base_list()
        self._refresh_iteration_group_choices()
        self.reset_prompt_base_form()
        QMessageBox.information(
            self,
            "Importar catálogo Dollimages",
            f"Importación completada.\nPrompts base: {imported_bases}\nVariaciones: {imported_variations}",
        )
        self.catalog_updated.emit()

    def _build_iteration_group_list(self) -> None:
        self.prompt_base_iterations_list.clear()
        for key, label in self.ITERATION_GROUP_OPTIONS:
            item = QListWidgetItem(f"{label} ({key})")
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.prompt_base_iterations_list.addItem(item)

    def _refresh_iteration_group_choices(self) -> None:
        current = self.prompt_base_group_combo.currentData()
        groups = self.store.list_prompt_variation_groups(include_disabled=True)
        self.prompt_base_group_combo.blockSignals(True)
        self.prompt_base_group_combo.clear()
        self.prompt_base_group_combo.addItem("Selecciona grupo...", None)
        for group in groups:
            self.prompt_base_group_combo.addItem(group, group)
        if current:
            idx = self.prompt_base_group_combo.findData(current)
            if idx >= 0:
                self.prompt_base_group_combo.setCurrentIndex(idx)
        self.prompt_base_group_combo.blockSignals(False)

    def add_iteration_group(self) -> None:
        group_key = self.prompt_base_group_input.text().strip()
        if not group_key:
            combo_value = self.prompt_base_group_combo.currentData()
            if isinstance(combo_value, str):
                group_key = combo_value.strip()
        if not group_key:
            QMessageBox.warning(self, "Prompts base", "Introduce una clave de grupo.")
            return

        existing = {
            str(self.prompt_base_iterations_list.item(i).data(Qt.UserRole)).lower()
            for i in range(self.prompt_base_iterations_list.count())
        }
        if group_key.lower() in existing:
            QMessageBox.information(self, "Prompts base", "Ese grupo ya está en la lista.")
            return

        item = QListWidgetItem(group_key)
        item.setData(Qt.UserRole, group_key)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.prompt_base_iterations_list.addItem(item)
        self.prompt_base_group_input.clear()
        self.prompt_base_group_combo.setCurrentIndex(0)

    def _checked_iteration_groups(self) -> list[str]:
        groups: list[str] = []
        for idx in range(self.prompt_base_iterations_list.count()):
            item = self.prompt_base_iterations_list.item(idx)
            if item.checkState() == Qt.Checked:
                group_key = item.data(Qt.UserRole)
                if group_key:
                    groups.append(str(group_key))
        return groups

    def _set_checked_iteration_groups(self, groups: list[str]) -> None:
        normalized = {str(group).strip().lower() for group in groups if str(group).strip()}
        existing = {
            str(self.prompt_base_iterations_list.item(i).data(Qt.UserRole)).lower()
            for i in range(self.prompt_base_iterations_list.count())
        }
        for group in groups:
            group_key = str(group).strip()
            if not group_key:
                continue
            group_lower = group_key.lower()
            if group_lower in existing:
                continue
            item = QListWidgetItem(group_key)
            item.setData(Qt.UserRole, group_key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.prompt_base_iterations_list.addItem(item)
            existing.add(group_lower)

        for idx in range(self.prompt_base_iterations_list.count()):
            item = self.prompt_base_iterations_list.item(idx)
            group_key = str(item.data(Qt.UserRole) or "").strip()
            if group_key and group_key.lower() in normalized:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
