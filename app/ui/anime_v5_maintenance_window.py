from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.data.storage import get_store


class AnimeV5MaintenanceWindow(QMainWindow):
    catalog_updated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mantenimiento Anime V5")
        self.resize(1040, 700)
        self.store = get_store()
        self._character_rows: list[dict[str, object]] = []
        self._prompt_rows: list[dict[str, object]] = []

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        intro = QLabel(
            "Gestiona independientemente listas, personajes, anime/descripciones y prompts reutilizables. "
            "La opción Anime V5 consume estas listas para generar imágenes."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(intro)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        tabs.addTab(self._build_character_tab(), "Listas y personajes")
        tabs.addTab(self._build_prompt_tab(), "Prompts")

        self.character_table.itemSelectionChanged.connect(self._load_selected_character)
        self.character_list_filter.currentIndexChanged.connect(self._refresh_character_table)
        self.character_save_btn.clicked.connect(self.save_character)
        self.character_new_btn.clicked.connect(self.reset_character_form)
        self.character_delete_btn.clicked.connect(self.delete_character)
        self.list_delete_btn.clicked.connect(self.delete_character_list)
        self.prompt_table.itemSelectionChanged.connect(self._load_selected_prompt)
        self.prompt_save_btn.clicked.connect(self.save_prompt)
        self.prompt_new_btn.clicked.connect(self.reset_prompt_form)
        self.prompt_delete_btn.clicked.connect(self.delete_prompt)

        self.refresh_all()

    def _build_character_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Lista:"))
        self.character_list_filter = QComboBox()
        self.character_list_filter.addItem("Todas", None)
        filter_row.addWidget(self.character_list_filter)
        self.list_delete_btn = QPushButton("Eliminar lista")
        filter_row.addWidget(self.list_delete_btn)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.character_table = QTableWidget(0, 5)
        self.character_table.setHorizontalHeaderLabels(["ID", "Lista / Anime", "Personaje", "Descripción", "Activo"])
        self.character_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.character_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.character_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.character_table.verticalHeader().setVisible(False)
        self.character_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.character_table, 1)

        form = QGroupBox("Crear / editar personaje")
        grid = QGridLayout(form)
        grid.addWidget(QLabel("ID:"), 0, 0)
        self.character_id_label = QLabel("—")
        grid.addWidget(self.character_id_label, 0, 1)
        self.character_enabled_checkbox = QCheckBox("Activo")
        self.character_enabled_checkbox.setChecked(True)
        grid.addWidget(self.character_enabled_checkbox, 0, 2)
        grid.addWidget(QLabel("Lista / Anime:"), 1, 0)
        self.character_list_input = QLineEdit()
        self.character_list_input.setPlaceholderText("Ej: One Piece")
        grid.addWidget(self.character_list_input, 1, 1, 1, 3)
        grid.addWidget(QLabel("Personaje:"), 2, 0)
        self.character_name_input = QLineEdit()
        self.character_name_input.setPlaceholderText("Ej: Nami")
        grid.addWidget(self.character_name_input, 2, 1, 1, 3)
        grid.addWidget(QLabel("Descripción:"), 3, 0)
        self.character_description_input = QPlainTextEdit()
        self.character_description_input.setPlaceholderText("Descripción visual estable para [description]")
        self.character_description_input.setMinimumHeight(90)
        grid.addWidget(self.character_description_input, 3, 1, 1, 3)
        actions = QHBoxLayout()
        self.character_save_btn = QPushButton("Guardar personaje")
        self.character_new_btn = QPushButton("Nuevo")
        self.character_delete_btn = QPushButton("Eliminar personaje")
        actions.addWidget(self.character_save_btn)
        actions.addWidget(self.character_new_btn)
        actions.addWidget(self.character_delete_btn)
        actions.addStretch(1)
        grid.addLayout(actions, 4, 1, 1, 3)
        layout.addWidget(form)
        return tab

    def _build_prompt_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.prompt_table = QTableWidget(0, 4)
        self.prompt_table.setHorizontalHeaderLabels(["ID", "Título", "Prompt", "Activo"])
        self.prompt_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.prompt_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.prompt_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.prompt_table.verticalHeader().setVisible(False)
        self.prompt_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.prompt_table, 1)

        form = QGroupBox("Crear / editar prompt")
        grid = QGridLayout(form)
        grid.addWidget(QLabel("ID:"), 0, 0)
        self.prompt_id_label = QLabel("—")
        grid.addWidget(self.prompt_id_label, 0, 1)
        self.prompt_enabled_checkbox = QCheckBox("Activo")
        self.prompt_enabled_checkbox.setChecked(True)
        grid.addWidget(self.prompt_enabled_checkbox, 0, 2)
        grid.addWidget(QLabel("Título:"), 1, 0)
        self.prompt_title_input = QLineEdit()
        grid.addWidget(self.prompt_title_input, 1, 1, 1, 3)
        grid.addWidget(QLabel("Prompt:"), 2, 0)
        self.prompt_text_input = QPlainTextEdit()
        self.prompt_text_input.setPlaceholderText("Usa [personaje], [anime], [description] y opciones Anime V5 si aplica.")
        self.prompt_text_input.setMinimumHeight(150)
        grid.addWidget(self.prompt_text_input, 2, 1, 1, 3)
        actions = QHBoxLayout()
        self.prompt_save_btn = QPushButton("Guardar prompt")
        self.prompt_new_btn = QPushButton("Nuevo")
        self.prompt_delete_btn = QPushButton("Eliminar prompt")
        actions.addWidget(self.prompt_save_btn)
        actions.addWidget(self.prompt_new_btn)
        actions.addWidget(self.prompt_delete_btn)
        actions.addStretch(1)
        grid.addLayout(actions, 3, 1, 1, 3)
        layout.addWidget(form)
        return tab

    def refresh_all(self) -> None:
        current_list = self.character_list_filter.currentData()
        lists = sorted(self.store.list_anime_character_lists(include_disabled=True).keys())
        self.character_list_filter.blockSignals(True)
        self.character_list_filter.clear()
        self.character_list_filter.addItem("Todas", None)
        for list_name in lists:
            self.character_list_filter.addItem(list_name, list_name)
        if current_list:
            idx = self.character_list_filter.findData(current_list)
            if idx >= 0:
                self.character_list_filter.setCurrentIndex(idx)
        self.character_list_filter.blockSignals(False)
        self._refresh_character_table()
        self._refresh_prompt_table()

    def _refresh_character_table(self) -> None:
        list_name = self.character_list_filter.currentData()
        self._character_rows = self.store.list_anime_characters(list_name=list_name, include_disabled=True)
        self.character_table.setRowCount(len(self._character_rows))
        for row_idx, row in enumerate(self._character_rows):
            values = [row["id"], row["list_name"], row["name"], row["description"], "Sí" if row["enabled"] else "No"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, row)
                self.character_table.setItem(row_idx, col, item)
        self.character_table.resizeColumnsToContents()

    def _refresh_prompt_table(self) -> None:
        self._prompt_rows = self.store.list_anime_prompts(include_disabled=True)
        self.prompt_table.setRowCount(len(self._prompt_rows))
        for row_idx, row in enumerate(self._prompt_rows):
            values = [row["id"], row["title"], row["prompt_text"], "Sí" if row["enabled"] else "No"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, row)
                self.prompt_table.setItem(row_idx, col, item)
        self.prompt_table.resizeColumnsToContents()

    def _selected_row(self, table: QTableWidget) -> dict[str, object] | None:
        selected = table.selectionModel().selectedRows()
        if not selected:
            return None
        item = table.item(selected[0].row(), 0)
        data = item.data(Qt.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _load_selected_character(self) -> None:
        row = self._selected_row(self.character_table)
        if not row:
            return
        self.character_id_label.setText(str(row["id"]))
        self.character_list_input.setText(str(row["list_name"]))
        self.character_name_input.setText(str(row["name"]))
        self.character_description_input.setPlainText(str(row["description"]))
        self.character_enabled_checkbox.setChecked(bool(row["enabled"]))

    def reset_character_form(self) -> None:
        self.character_table.clearSelection()
        self.character_id_label.setText("—")
        selected_list = self.character_list_filter.currentData()
        self.character_list_input.setText(str(selected_list or ""))
        self.character_name_input.clear()
        self.character_description_input.clear()
        self.character_enabled_checkbox.setChecked(True)

    def save_character(self) -> None:
        list_name = self.character_list_input.text().strip()
        name = self.character_name_input.text().strip()
        if not list_name or not name:
            QMessageBox.warning(self, "Anime V5", "La lista/anime y el personaje son obligatorios.")
            return
        current_id = self.character_id_label.text()
        saved_id = self.store.save_anime_character(
            character_id=int(current_id) if current_id.isdigit() else None,
            list_name=list_name,
            name=name,
            description=self.character_description_input.toPlainText().strip(),
            enabled=self.character_enabled_checkbox.isChecked(),
        )
        self.refresh_all()
        self._select_table_id(self.character_table, saved_id)
        self.catalog_updated.emit()
        QMessageBox.information(self, "Anime V5", "Personaje guardado.")

    def delete_character(self) -> None:
        row = self._selected_row(self.character_table)
        if not row:
            QMessageBox.warning(self, "Anime V5", "Selecciona un personaje.")
            return
        if QMessageBox.question(self, "Eliminar", f"¿Eliminar {row['name']} de {row['list_name']}?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.store.delete_anime_character(character_id=int(row["id"]))
        self.refresh_all()
        self.reset_character_form()
        self.catalog_updated.emit()

    def delete_character_list(self) -> None:
        list_name = self.character_list_filter.currentData()
        if not list_name:
            QMessageBox.warning(self, "Anime V5", "Selecciona una lista concreta.")
            return
        if QMessageBox.question(self, "Eliminar lista", f"¿Eliminar la lista completa '{list_name}'?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.store.delete_anime_character_list(list_name=str(list_name))
        self.refresh_all()
        self.reset_character_form()
        self.catalog_updated.emit()

    def _load_selected_prompt(self) -> None:
        row = self._selected_row(self.prompt_table)
        if not row:
            return
        self.prompt_id_label.setText(str(row["id"]))
        self.prompt_title_input.setText(str(row["title"]))
        self.prompt_text_input.setPlainText(str(row["prompt_text"]))
        self.prompt_enabled_checkbox.setChecked(bool(row["enabled"]))

    def reset_prompt_form(self) -> None:
        self.prompt_table.clearSelection()
        self.prompt_id_label.setText("—")
        self.prompt_title_input.clear()
        self.prompt_text_input.clear()
        self.prompt_enabled_checkbox.setChecked(True)

    def save_prompt(self) -> None:
        title = self.prompt_title_input.text().strip()
        prompt_text = self.prompt_text_input.toPlainText().strip()
        if not title or not prompt_text:
            QMessageBox.warning(self, "Anime V5", "El título y el prompt son obligatorios.")
            return
        current_id = self.prompt_id_label.text()
        saved_id = self.store.save_anime_prompt(
            prompt_id=int(current_id) if current_id.isdigit() else None,
            title=title,
            prompt_text=prompt_text,
            enabled=self.prompt_enabled_checkbox.isChecked(),
        )
        self.refresh_all()
        self._select_table_id(self.prompt_table, saved_id)
        self.catalog_updated.emit()
        QMessageBox.information(self, "Anime V5", "Prompt guardado.")

    def delete_prompt(self) -> None:
        row = self._selected_row(self.prompt_table)
        if not row:
            QMessageBox.warning(self, "Anime V5", "Selecciona un prompt.")
            return
        if QMessageBox.question(self, "Eliminar", f"¿Eliminar el prompt '{row['title']}'?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.store.delete_anime_prompt(prompt_id=int(row["id"]))
        self.refresh_all()
        self.reset_prompt_form()
        self.catalog_updated.emit()

    def _select_table_id(self, table: QTableWidget, row_id: int) -> None:
        for row_idx in range(table.rowCount()):
            item = table.item(row_idx, 0)
            if item and item.text() == str(row_id):
                table.selectRow(row_idx)
                break
