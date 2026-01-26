from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton


class PromptDetailDialog(QDialog):
    copyRequested = Signal(int, str)
    retryRequested = Signal(int)
    deleteRequested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prompt")
        self.setMinimumSize(520, 360)
        self.setWindowModality(Qt.ApplicationModal)

        self._prompt_id: int | None = None
        self._prompt_text: str = "—"

        layout = QVBoxLayout(self)

        self.prompt_id_label = QLabel("Prompt ID: —")
        self.prompt_id_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.prompt_id_label)

        self.prompt_text = QPlainTextEdit("—")
        self.prompt_text.setReadOnly(True)
        self.prompt_text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        layout.addWidget(self.prompt_text)

        self.backend_status_label = QLabel("Backend: —")
        self.backend_status_label.setStyleSheet("color: #c0c0c0;")
        layout.addWidget(self.backend_status_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.copy_btn = QPushButton("Copiar prompt")
        self.retry_btn = QPushButton("Reintentar prompt")
        self.delete_btn = QPushButton("Eliminar prompt")
        self.close_btn = QPushButton("Cerrar prompt")
        actions.addWidget(self.copy_btn)
        actions.addWidget(self.retry_btn)
        actions.addWidget(self.delete_btn)
        actions.addWidget(self.close_btn)
        layout.addLayout(actions)

        self.copy_btn.clicked.connect(self._emit_copy)
        self.retry_btn.clicked.connect(self._emit_retry)
        self.delete_btn.clicked.connect(self._emit_delete)
        self.close_btn.clicked.connect(self.close)

    def set_prompt_data(self, prompt_id: int, prompt_text: str, backend_status: str | None) -> None:
        self._prompt_id = prompt_id
        self._prompt_text = prompt_text
        self.prompt_id_label.setText(f"Prompt ID: {prompt_id}")
        self.prompt_text.setPlainText(prompt_text)
        if backend_status:
            self.backend_status_label.setText(f"Backend: {backend_status}")
        else:
            self.backend_status_label.setText("Backend: —")

    def _emit_copy(self) -> None:
        if self._prompt_id is None:
            return
        self.copyRequested.emit(self._prompt_id, self._prompt_text)

    def _emit_retry(self) -> None:
        if self._prompt_id is None:
            return
        self.retryRequested.emit(self._prompt_id)

    def _emit_delete(self) -> None:
        if self._prompt_id is None:
            return
        self.deleteRequested.emit(self._prompt_id)
