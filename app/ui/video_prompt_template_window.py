from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.data.repositories import VideoPromptTemplateRow
from app.data.storage import get_store


DEFAULT_VIDEO_PROMPT_TEMPLATES: list[dict[str, str]] = [
    {
        "title": "Movimiento suave de cámara",
        "prompt_text": "slow cinematic camera dolly in, subtle parallax, natural body motion, detailed lighting",
    },
    {
        "title": "Loop vertical para redes",
        "prompt_text": "loopable motion, smooth breathing and hair movement, stable framing, soft cinematic shadows",
    },
]


class VideoPromptTemplateWindow(QMainWindow):
    catalog_updated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mantenimiento de prompts tipo para video")
        self.resize(780, 430)

        self.store = get_store()
        self._template_map: dict[int, VideoPromptTemplateRow] = {}

        try:
            self.store.ensure_video_prompt_templates_seeded(DEFAULT_VIDEO_PROMPT_TEMPLATES)
        except Exception as exc:
            print(f"[WARN] No se pudieron inicializar prompts tipo de video: {exc}")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        group = QGroupBox("Prompts tipo para Image2Vid")
        group_layout = QVBoxLayout(group)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Prompt tipo:"))
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(360)
        select_row.addWidget(self.template_combo)
        select_row.addWidget(QLabel("ID:"))
        self.template_id_label = QLabel("—")
        select_row.addWidget(self.template_id_label)
        self.template_enabled_checkbox = QCheckBox("Habilitado")
        self.template_enabled_checkbox.setChecked(True)
        select_row.addWidget(self.template_enabled_checkbox)
        select_row.addStretch(1)
        group_layout.addLayout(select_row)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Título:"))
        self.template_title_input = QLineEdit()
        self.template_title_input.setPlaceholderText("Ej: Cámara orbital lenta")
        title_row.addWidget(self.template_title_input)
        group_layout.addLayout(title_row)

        group_layout.addWidget(QLabel("Prompt:"))
        self.template_prompt_input = QPlainTextEdit()
        self.template_prompt_input.setPlaceholderText("Texto base reutilizable para generación de video")
        self.template_prompt_input.setMinimumHeight(170)
        group_layout.addWidget(self.template_prompt_input)

        actions = QHBoxLayout()
        self.save_btn = QPushButton("Guardar")
        self.new_btn = QPushButton("Nuevo")
        self.delete_btn = QPushButton("Eliminar")
        actions.addWidget(self.save_btn)
        actions.addWidget(self.new_btn)
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        group_layout.addLayout(actions)

        layout.addWidget(group)
        layout.addStretch(1)

        self.template_combo.currentIndexChanged.connect(self.load_template_from_combo)
        self.save_btn.clicked.connect(self.save_template)
        self.new_btn.clicked.connect(self.reset_form)
        self.delete_btn.clicked.connect(self.delete_template)

        self._refresh_template_list()
        self.reset_form()

    def _refresh_template_list(self) -> None:
        current_id = self.template_combo.currentData()
        rows = self.store.list_video_prompt_templates(include_disabled=True)
        self._template_map = {row.id: row for row in rows}

        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("Nuevo...", None)
        for row in rows:
            label = row.title
            if not row.enabled:
                label = f"{label} (deshabilitado)"
            self.template_combo.addItem(label, row.id)
        if current_id:
            idx = self.template_combo.findData(current_id)
            if idx >= 0:
                self.template_combo.setCurrentIndex(idx)
        self.template_combo.blockSignals(False)

    def reset_form(self) -> None:
        self.template_combo.setCurrentIndex(0)
        self.template_id_label.setText("—")
        self.template_title_input.clear()
        self.template_prompt_input.clear()
        self.template_enabled_checkbox.setChecked(True)

    def load_template_from_combo(self) -> None:
        template_id = self.template_combo.currentData()
        if not template_id:
            self.reset_form()
            return
        row = self._template_map.get(int(template_id))
        if not row:
            return
        self.template_id_label.setText(str(row.id))
        self.template_title_input.setText(row.title)
        self.template_prompt_input.setPlainText(row.prompt_text)
        self.template_enabled_checkbox.setChecked(row.enabled)

    def save_template(self) -> None:
        template_id = self.template_combo.currentData()
        title = self.template_title_input.text().strip()
        prompt_text = self.template_prompt_input.toPlainText().strip()
        enabled = self.template_enabled_checkbox.isChecked()

        if not title:
            QMessageBox.warning(self, "Prompts tipo video", "El título es obligatorio.")
            return
        if not prompt_text:
            QMessageBox.warning(self, "Prompts tipo video", "El prompt no puede estar vacío.")
            return

        saved_id = self.store.save_video_prompt_template(
            template_id=int(template_id) if template_id else None,
            title=title,
            prompt_text=prompt_text,
            enabled=enabled,
        )

        self._refresh_template_list()
        idx = self.template_combo.findData(saved_id)
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "Prompts tipo video", "Prompt tipo guardado.")
        self.catalog_updated.emit()

    def delete_template(self) -> None:
        template_id = self.template_combo.currentData()
        if not template_id:
            QMessageBox.warning(self, "Prompts tipo video", "Selecciona un prompt tipo para eliminar.")
            return

        row = self._template_map.get(int(template_id))
        label = row.title if row else f"Prompt tipo #{template_id}"
        confirm = QMessageBox.question(
            self,
            "Eliminar",
            f"¿Quieres eliminar este prompt tipo?\n\n{label}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.store.delete_video_prompt_template(template_id=int(template_id))
        self._refresh_template_list()
        self.reset_form()
        QMessageBox.information(self, "Prompts tipo video", "Prompt tipo eliminado.")
        self.catalog_updated.emit()
