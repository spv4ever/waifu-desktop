from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.x_media_service import XMediaService


class XDownloadThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service: XMediaService, url: str) -> None:
        super().__init__()
        self.service = service
        self.url = url

    def run(self) -> None:
        try:
            self.succeeded.emit(self.service.download(self.url))
        except Exception as exc:
            self.failed.emit(str(exc))


class SocialToolsWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Waifu Desktop — Herramientas de redes")
        self.resize(1050, 650)
        self.service = XMediaService()
        self.download_thread: XDownloadThread | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Herramientas de redes")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Descarga y cataloga imágenes, vídeos y grabaciones públicas de X")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        generation_btn = QPushButton("← Generación de imagen")
        generation_btn.clicked.connect(self.close)
        heading.addWidget(generation_btn)
        layout.addLayout(heading)

        form = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://x.com/usuario/status/...")
        self.url_input.returnPressed.connect(self.start_download)
        self.download_btn = QPushButton("Descargar contenido")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.clicked.connect(self.start_download)
        form.addWidget(self.url_input, 1)
        form.addWidget(self.download_btn)
        layout.addLayout(form)

        self.status_label = QLabel("Solo se procesan publicaciones accesibles públicamente.")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Título", "Descripción", "Autor", "Contenido local", "Fecha"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_selected_content)
        self.table.itemSelectionChanged.connect(self._update_action_buttons)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.open_folder_btn = QPushButton("Abrir carpeta del post")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self.open_selected_folder)
        self.open_btn = QPushButton("Ver contenido descargado")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_selected_content)
        self.refresh_btn = QPushButton("Actualizar biblioteca")
        self.refresh_btn.clicked.connect(self.refresh)
        actions.addWidget(self.open_folder_btn)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.refresh_btn)
        layout.addLayout(actions)
        self.refresh()

    def start_download(self) -> None:
        if self.download_thread and self.download_thread.isRunning():
            return
        try:
            url = self.service.validate_url(self.url_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Enlace no válido", str(exc))
            return
        self.download_btn.setEnabled(False)
        self.status_label.setText("Descargando y extrayendo los datos de la publicación…")
        self.download_thread = XDownloadThread(self.service, url)
        self.download_thread.succeeded.connect(self._download_finished)
        self.download_thread.failed.connect(self._download_failed)
        self.download_thread.finished.connect(lambda: self.download_btn.setEnabled(True))
        self.download_thread.start()

    def _download_finished(self, post: object) -> None:
        self.url_input.clear()
        self.status_label.setText("Contenido descargado y guardado en la biblioteca local.")
        self.refresh()

    def _download_failed(self, message: str) -> None:
        self.status_label.setText("No se pudo completar la descarga.")
        QMessageBox.critical(self, "Error de descarga", message)

    def refresh(self) -> None:
        posts = self.service.list_posts()
        self.table.clearSelection()
        self.table.setRowCount(len(posts))
        for row, post in enumerate(posts):
            paths = [asset.local_path for asset in post.assets]
            values = [post.title, post.description, post.author or "—", f"{len(paths)} archivo(s)", post.created_at]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 3:
                    item.setData(256, paths)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        has_selection = self.table.selectionModel().hasSelection()
        self.open_folder_btn.setEnabled(has_selection)
        self.open_btn.setEnabled(has_selection)

    def open_selected_folder(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Biblioteca", "Selecciona una publicación primero.")
            return
        paths = self.table.item(row, 3).data(256) or []
        folder = next((Path(path).parent for path in paths if Path(path).parent.is_dir()), None)
        if folder is None:
            QMessageBox.warning(
                self,
                "Carpeta no disponible",
                "No se encuentra la carpeta con el contenido de la publicación.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_selected_content(self, *_args: object) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Biblioteca", "Selecciona una publicación primero.")
            return
        paths = self.table.item(row, 3).data(256) or []
        existing = next((Path(path) for path in paths if Path(path).exists()), None)
        if existing is None:
            QMessageBox.warning(self, "Contenido no disponible", "No se encuentra el archivo descargado.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(existing)))
