from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QDoubleSpinBox, QVBoxLayout, QWidget,
)

from app.services.short_creator_service import ShortCreationResult, ShortCreatorService


class ShortCreatorThread(QThread):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service: ShortCreatorService, **kwargs: object) -> None:
        super().__init__()
        self.service = service
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            result = self.service.create_shorts(**self.kwargs, progress_callback=self.progress.emit)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


class ShortCreatorWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Waifu Desktop — Creador de Shorts")
        self.resize(760, 520)
        self.service = ShortCreatorService()
        self.thread: ShortCreatorThread | None = None
        self.result: ShortCreationResult | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Creador de YouTube Shorts")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Convierte un vídeo 16:9 en fragmentos 9:16 mediante un recorte vertical centrado. "
            "La imagen no se escala y cada fragmento conserva el audio original que le corresponde."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("AppSubtitle")
        layout.addWidget(subtitle)

        group = QGroupBox("Vídeo original y publicación")
        form = QFormLayout(group)
        source_row = QHBoxLayout()
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Selecciona un vídeo horizontal 16:9…")
        browse = QPushButton("Examinar…")
        browse.clicked.connect(self._browse)
        source_row.addWidget(self.source_input, 1)
        source_row.addWidget(browse)
        form.addRow("Fichero de vídeo:", source_row)
        self.song_input = QLineEdit()
        self.song_input.setPlaceholderText("Nombre de la canción")
        form.addRow("Canción:", self.song_input)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=…")
        form.addRow("Vídeo completo:", self.url_input)
        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(1, 180)
        self.duration_input.setValue(60)
        self.duration_input.setSuffix(" s")
        form.addRow("Duración por Short:", self.duration_input)
        self.count_input = QSpinBox()
        self.count_input.setRange(1, 100)
        self.count_input.setValue(5)
        form.addRow("Número de Shorts:", self.count_input)
        layout.addWidget(group)

        note = QLabel(
            "Se generarán hasta el número indicado; si el vídeo termina antes, el último Short "
            "usará solo el tiempo restante. Cada MP4 tendrá un TXT con 3 propuestas de post y el enlace al original."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel("Listo para crear los Shorts.")
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.open_folder_btn = QPushButton("Abrir carpeta de salida")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._open_folder)
        self.create_btn = QPushButton("Crear Shorts")
        self.create_btn.setObjectName("PrimaryButton")
        self.create_btn.clicked.connect(self._create)
        actions.addWidget(self.open_folder_btn)
        actions.addStretch()
        actions.addWidget(self.create_btn)
        layout.addLayout(actions)

    def _browse(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar vídeo 16:9", "", "Vídeos (*.mp4 *.mov *.m4v *.mkv *.webm *.avi)"
        )
        if filename:
            self.source_input.setText(filename)
            if not self.song_input.text().strip():
                self.song_input.setText(Path(filename).stem.replace("_", " "))

    def _create(self) -> None:
        if self.thread and self.thread.isRunning():
            return
        self.create_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.status.setText("Analizando el vídeo…")
        self.thread = ShortCreatorThread(
            self.service,
            source_video=self.source_input.text(),
            clip_seconds=self.duration_input.value(),
            clip_count=self.count_input.value(),
            song_title=self.song_input.text(),
            youtube_url=self.url_input.text(),
        )
        self.thread.progress.connect(self.status.setText)
        self.thread.succeeded.connect(self._finished)
        self.thread.failed.connect(self._failed)
        self.thread.finished.connect(lambda: self.create_btn.setEnabled(True))
        self.thread.start()

    def _finished(self, result: object) -> None:
        self.result = result  # type: ignore[assignment]
        self.open_folder_btn.setEnabled(True)
        self.status.setText(f"Listo: {len(self.result.clips)} Shorts creados en {self.result.folder}")
        QMessageBox.information(self, "Shorts creados", self.status.text())

    def _failed(self, message: str) -> None:
        self.status.setText("No se pudieron crear los Shorts.")
        QMessageBox.critical(self, "Error al crear Shorts", message)

    def _open_folder(self) -> None:
        if self.result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.folder)))
