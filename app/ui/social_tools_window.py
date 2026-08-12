from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QComboBox,
    QGroupBox,
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

from app.services.x_media_service import SocialMediaService
from app.services.x_share_service import XShareError, XShareService


class SocialDownloadThread(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service: SocialMediaService, url: str) -> None:
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
        self.service = SocialMediaService()
        self.x_share_service = XShareService()
        self.download_thread: SocialDownloadThread | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Herramientas de redes")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Descarga y cataloga contenido público de X, Instagram, TikTok y YouTube")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        heading.addLayout(titles)
        heading.addStretch()
        generation_btn = QPushButton("← Generación de imagen")
        generation_btn.clicked.connect(self.close)
        heading.addWidget(generation_btn)
        layout.addLayout(heading)

        share_group = QGroupBox("Compartir X")
        share_layout = QVBoxLayout(share_group)
        share_help = QLabel(
            "Elige categoría, subcategoría y versión. Se seleccionarán 4 imágenes al azar sin "
            "mezclar versiones y se abrirá "
            "el compositor de X con el copy y los hashtags. Debes tener x.com abierto y tu sesión iniciada."
        )
        share_help.setWordWrap(True)
        share_layout.addWidget(share_help)
        share_form = QHBoxLayout()
        share_form.addWidget(QLabel("Categoría:"))
        self.x_category_combo = QComboBox()
        share_form.addWidget(self.x_category_combo, 1)
        share_form.addWidget(QLabel("Subcategoría:"))
        self.x_subcategory_combo = QComboBox()
        share_form.addWidget(self.x_subcategory_combo, 1)
        share_form.addWidget(QLabel("Versión:"))
        self.x_version_combo = QComboBox()
        share_form.addWidget(self.x_version_combo, 1)
        self.share_x_btn = QPushButton("Compartir X")
        self.share_x_btn.setObjectName("PrimaryButton")
        share_form.addWidget(self.share_x_btn)
        share_layout.addLayout(share_form)
        layout.addWidget(share_group)

        self.x_category_combo.currentIndexChanged.connect(self._populate_x_subcategories)
        self.x_subcategory_combo.currentIndexChanged.connect(self._populate_x_versions)
        self.share_x_btn.clicked.connect(self.share_x)
        self._populate_x_options()

        form = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enlace de X, Instagram, TikTok o YouTube")
        self.url_input.returnPressed.connect(self.start_download)
        self.download_btn = QPushButton("Descargar contenido")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.clicked.connect(self.start_download)
        form.addWidget(self.url_input, 1)
        form.addWidget(self.download_btn)
        layout.addLayout(form)

        self.status_label = QLabel("Solo se procesa contenido accesible públicamente.")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Red", "Título", "Descripción", "Autor", "Contenido local", "Fecha"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.open_selected_content)
        self.table.itemSelectionChanged.connect(self._update_action_buttons)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.copy_title_btn = QPushButton("Copiar título")
        self.copy_title_btn.setEnabled(False)
        self.copy_title_btn.clicked.connect(self.copy_selected_title)
        self.copy_description_btn = QPushButton("Copiar descripción")
        self.copy_description_btn.setEnabled(False)
        self.copy_description_btn.clicked.connect(self.copy_selected_description)
        self.open_folder_btn = QPushButton("Abrir carpeta del post")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self.open_selected_folder)
        self.open_btn = QPushButton("Ver contenido descargado")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_selected_content)
        self.refresh_btn = QPushButton("Actualizar biblioteca")
        self.refresh_btn.clicked.connect(self.refresh)
        actions.addWidget(self.copy_title_btn)
        actions.addWidget(self.copy_description_btn)
        actions.addWidget(self.open_folder_btn)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.refresh_btn)
        layout.addLayout(actions)
        self.refresh()

    def _populate_x_options(self) -> None:
        self._x_options = self.x_share_service.options()
        self.x_category_combo.clear()
        for category in self._x_options:
            self.x_category_combo.addItem(category, category)
        self._populate_x_subcategories()

    def _populate_x_subcategories(self) -> None:
        category = str(self.x_category_combo.currentData() or "")
        self.x_subcategory_combo.clear()
        for subcategory in self._x_options.get(category, {}):
            self.x_subcategory_combo.addItem(subcategory, subcategory)
        self._populate_x_versions()

    def _populate_x_versions(self) -> None:
        category = str(self.x_category_combo.currentData() or "")
        subcategory = str(self.x_subcategory_combo.currentData() or "")
        self.x_version_combo.clear()
        for version in self._x_options.get(category, {}).get(subcategory, []):
            self.x_version_combo.addItem(version, version)
        self.share_x_btn.setEnabled(bool(category and subcategory and self.x_version_combo.count()))

    def share_x(self) -> None:
        category = str(self.x_category_combo.currentData() or "")
        subcategory = str(self.x_subcategory_combo.currentData() or "")
        version = str(self.x_version_combo.currentData() or "")
        try:
            draft = self.x_share_service.create_draft(category, subcategory, version)
        except XShareError as exc:
            QMessageBox.warning(self, "Compartir X", str(exc))
            return

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in draft.images])
        mime.setText("\n".join(str(path) for path in draft.images))
        QApplication.clipboard().setMimeData(mime)
        if not QDesktopServices.openUrl(QUrl(draft.compose_url)):
            QMessageBox.critical(self, "Compartir X", "No se pudo abrir x.com en el navegador.")
            return
        self.status_label.setText("X abierto: pega con Ctrl+V para adjuntar las 4 imágenes y publica.")
        QMessageBox.information(
            self,
            "Compartir X — último paso",
            "El copy ya está cargado en X y las 4 imágenes están en el portapapeles.\n\n"
            "En la ventana de x.com, pulsa Ctrl+V para adjuntarlas y revisa el post antes de publicar.",
        )

    def start_download(self) -> None:
        if self.download_thread and self.download_thread.isRunning():
            return
        try:
            url = self.service.validate_url(self.url_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Enlace no válido", str(exc))
            return
        self.download_btn.setEnabled(False)
        self.status_label.setText("Descargando y extrayendo los datos del contenido…")
        self.download_thread = SocialDownloadThread(self.service, url)
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
            platform = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}.get(
                post.platform, "X"
            )
            values = [platform, post.title, post.description, post.author or "—", f"{len(paths)} archivo(s)", post.created_at]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 4:
                    item.setData(256, paths)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        has_selection = self.table.selectionModel().hasSelection()
        self.copy_title_btn.setEnabled(has_selection)
        self.copy_description_btn.setEnabled(has_selection)
        self.open_folder_btn.setEnabled(has_selection)
        self.open_btn.setEnabled(has_selection)

    def copy_selected_title(self) -> None:
        self._copy_selected_text(column=1, confirmation="Título copiado al portapapeles.")

    def copy_selected_description(self) -> None:
        self._copy_selected_text(column=2, confirmation="Descripción copiada al portapapeles.")

    def _copy_selected_text(self, *, column: int, confirmation: str) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, column) if row >= 0 else None
        if item is None:
            QMessageBox.information(self, "Biblioteca", "Selecciona una publicación primero.")
            return
        QApplication.clipboard().setText(item.text())
        self.status_label.setText(confirmation)

    def open_selected_folder(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Biblioteca", "Selecciona una publicación primero.")
            return
        paths = self.table.item(row, 4).data(256) or []
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
        paths = self.table.item(row, 4).data(256) or []
        existing = next((Path(path) for path in paths if Path(path).exists()), None)
        if existing is None:
            QMessageBox.warning(self, "Contenido no disponible", "No se encuentra el archivo descargado.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(existing)))
