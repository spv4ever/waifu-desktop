from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config.social_copies import load_social_copies
from app.data.repositories import SocialCopyRow
from app.data.storage import get_store


class SocialCopyWindow(QMainWindow):
    catalog_updated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mantenimiento de copys para redes sociales")
        self.resize(760, 420)

        self.store = get_store()
        self._copy_map: dict[int, SocialCopyRow] = {}

        try:
            templates = load_social_copies()
            self.store.ensure_social_copies_seeded(templates)
        except Exception as exc:
            print(f"[WARN] No se pudo cargar social_copies.yaml: {exc}")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        copy_group = QGroupBox("Copys para posts")
        copy_layout = QVBoxLayout(copy_group)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Copy existente:"))
        self.copy_combo = QComboBox()
        self.copy_combo.setMinimumWidth(320)
        select_row.addWidget(self.copy_combo)
        self.copy_enabled_checkbox = QCheckBox("Habilitado")
        self.copy_enabled_checkbox.setChecked(True)
        select_row.addWidget(self.copy_enabled_checkbox)
        select_row.addStretch(1)
        copy_layout.addLayout(select_row)

        text_row = QHBoxLayout()
        text_row.addWidget(QLabel("Texto:"))
        copy_layout.addLayout(text_row)
        self.copy_text_input = QPlainTextEdit()
        self.copy_text_input.setPlaceholderText("Texto del post. Usa {library}, {character} o {category}.")
        self.copy_text_input.setMinimumHeight(120)
        copy_layout.addWidget(self.copy_text_input)

        hashtag_row = QHBoxLayout()
        hashtag_row.addWidget(QLabel("Hashtags:"))
        copy_layout.addLayout(hashtag_row)
        self.copy_hashtags_input = QPlainTextEdit()
        self.copy_hashtags_input.setPlaceholderText("#anime #waifu #art")
        self.copy_hashtags_input.setMinimumHeight(80)
        copy_layout.addWidget(self.copy_hashtags_input)

        info_label = QLabel(
            "Variables disponibles: {library} (biblioteca), {character} (personaje), {category} (categoría)."
        )
        info_label.setWordWrap(True)
        copy_layout.addWidget(info_label)

        action_row = QHBoxLayout()
        self.save_btn = QPushButton("Guardar")
        self.new_btn = QPushButton("Nuevo")
        self.delete_btn = QPushButton("Eliminar")
        action_row.addWidget(self.save_btn)
        action_row.addWidget(self.new_btn)
        action_row.addWidget(self.delete_btn)
        action_row.addStretch(1)
        copy_layout.addLayout(action_row)

        layout.addWidget(copy_group)
        layout.addStretch(1)

        self.copy_combo.currentIndexChanged.connect(self.load_copy_from_combo)
        self.save_btn.clicked.connect(self.save_copy)
        self.new_btn.clicked.connect(self.reset_form)
        self.delete_btn.clicked.connect(self.delete_copy)

        self._refresh_copy_list()
        self.reset_form()

    def _refresh_copy_list(self) -> None:
        current_id = self.copy_combo.currentData()
        rows = self.store.list_social_copies(include_disabled=True)
        self._copy_map = {row.id: row for row in rows}
        self.copy_combo.blockSignals(True)
        self.copy_combo.clear()
        self.copy_combo.addItem("Nuevo...", None)
        for row in rows:
            preview = row.text.strip().replace("\n", " ")
            if len(preview) > 60:
                preview = f"{preview[:57]}..."
            label = preview or f"Copy #{row.id}"
            if not row.enabled:
                label = f"{label} (deshabilitado)"
            self.copy_combo.addItem(label, row.id)
        if current_id:
            idx = self.copy_combo.findData(current_id)
            if idx >= 0:
                self.copy_combo.setCurrentIndex(idx)
        self.copy_combo.blockSignals(False)

    def reset_form(self) -> None:
        self.copy_combo.setCurrentIndex(0)
        self.copy_text_input.clear()
        self.copy_hashtags_input.clear()
        self.copy_enabled_checkbox.setChecked(True)

    def load_copy_from_combo(self) -> None:
        copy_id = self.copy_combo.currentData()
        if not copy_id:
            return
        row = self._copy_map.get(int(copy_id))
        if not row:
            return
        self.copy_text_input.setPlainText(row.text)
        self.copy_hashtags_input.setPlainText(row.hashtags)
        self.copy_enabled_checkbox.setChecked(row.enabled)

    def save_copy(self) -> None:
        copy_id = self.copy_combo.currentData()
        text = self.copy_text_input.toPlainText().strip()
        hashtags = self.copy_hashtags_input.toPlainText().strip()
        enabled = self.copy_enabled_checkbox.isChecked()

        if not text:
            QMessageBox.warning(self, "Copys", "El texto del copy es obligatorio.")
            return

        saved_id = self.store.save_social_copy(
            copy_id=int(copy_id) if copy_id else None,
            text=text,
            hashtags=hashtags,
            enabled=enabled,
        )

        self._refresh_copy_list()
        idx = self.copy_combo.findData(saved_id)
        if idx >= 0:
            self.copy_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "Copys", "Copy guardado.")
        self.catalog_updated.emit()

    def delete_copy(self) -> None:
        copy_id = self.copy_combo.currentData()
        if not copy_id:
            QMessageBox.warning(self, "Copys", "Selecciona un copy para eliminar.")
            return

        row = self._copy_map.get(int(copy_id))
        row_text = row.text if row else f"Copy #{copy_id}"
        label = row_text[:60] + ("..." if len(row_text) > 60 else "")
        confirm = QMessageBox.question(
            self,
            "Eliminar",
            f"¿Quieres eliminar este copy?\n\n{label}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.store.delete_social_copy(copy_id=int(copy_id))
        self._refresh_copy_list()
        self.reset_form()
        QMessageBox.information(self, "Copys", "Copy eliminado.")
        self.catalog_updated.emit()
