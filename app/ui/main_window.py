from __future__ import annotations

import json
from pathlib import Path
from functools import partial
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PySide6.QtCore import Qt, QDateTime, QDate, QTime, QTimer, QUrl, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QSpinBox,
    QGroupBox, QComboBox, QAbstractItemView, QPlainTextEdit, QApplication, QDateTimeEdit,
    QLineEdit, QCheckBox, QDialog, QDoubleSpinBox, QFileDialog, QMenu, QStackedWidget,
    QHeaderView, QListWidget, QListWidgetItem, QSizePolicy,
)

from app.config.app_config import load_app_config
from app.config.waifu_catalog import load_waifu_catalog
from app.config.undress import (
    UNDRESS_FPS,
    UNDRESS_GARMENTS,
    build_undress_prompt,
    calculate_undress_duration,
)
from app.data.storage import get_store
from app.services.output_paths import build_output_path
from app.services.comfy_history_parser import extract_saved_video_output
from app.services.video_preview import resolve_video_preview_url
from app.services.pack_service import PackService
from app.services.dollimages_pack_service import DollimagesPackService
from app.services.file_open import open_file, open_folder_and_select
from app.services.checkpoint_service import CheckpointService
from app.services.reel_service import ReelService
from app.services.video_montage_service import VideoMontageService, BulkImagesYoutubeVideoResult
from app.services.manual_prompt_service import ManualPromptService
from app.services.dollimages_manual_prompt_service import DollimagesManualPromptService
from app.services.image2vid_service import ImageToVideoService
from app.services.anime_generation_service import AnimeGenerationService
from app.services.bulk_images_service import BulkImagesEnqueueRequest, BulkImagesService
from app.services.anime_v5_prompt_generator import (
    DEFAULT_TEMPLATE,
    DEFAULT_OPTIONS_PATH,
    choose_anime_v5_prompt_selection,
    fill_anime_v5_option_tokens,
    load_anime_v5_prompt_options,
)
from app.domain.models import (
    PackCreate,
    DollimagesPackCreate,
    ManualPromptCreate,
    DollimagesManualPromptCreate,
    ImageToVideoCreate,
    AnimeGenerationCreate,
)
from app.ui.data_source import (
    fetch_prompts,
    fetch_prompt_filters,
    fetch_prompt_status_counts,
    fetch_category_production_counts,
    fetch_dollimages_reel_available_count,
    fetch_dollimages_reel_group_counts,
    fetch_variants_for_category,
)
from app.ui.worker_thread import WorkerThread
from app.ui.refresh_worker import RefreshWorker, RefreshPayload
from app.ui.clickable_label import ClickableLabel
from app.ui.image_viewer import ImageViewer
from app.ui.prompt_base_window import PromptBaseWindow
from app.ui.prompt_variation_window import PromptVariationWindow
from app.ui.social_copy_window import SocialCopyWindow
from app.ui.prompt_dialog import PromptDetailDialog
from app.ui.dollimages_prompt_window import DollimagesPromptWindow
from app.ui.video_prompt_template_window import VideoPromptTemplateWindow
from app.ui.anime_v5_maintenance_window import AnimeV5MaintenanceWindow
from app.ui.bulk_images_prompt_window import BulkImagesPromptWindow
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QProxyStyle, QStyle

IMAGE2VID_MIN_NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，"
    "最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，"
    "畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)


class BulkYoutubeVideoThread(QThread):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service: VideoMontageService, **kwargs: Any) -> None:
        super().__init__()
        self.service = service
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            result = self.service.create_bulk_images_youtube_video(
                **self.kwargs,
                progress_callback=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)

class NoFocusRectStyle(QProxyStyle):
    """Elimina el rectángulo de foco (focus rect) que en Windows 11 aparece como marcas/lineas."""
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_FrameFocusRect:
            return
        super().drawPrimitive(element, option, painter, widget)


class VideoDropList(QListWidget):
    """Lista que acepta vídeos arrastrados desde el explorador de archivos."""

    _VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._has_video_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._has_video_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        paths = self._video_paths_from_mime(event.mimeData())
        if not paths:
            super().dropEvent(event)
            return
        self.add_video_paths(paths)
        event.acceptProposedAction()

    def _has_video_urls(self, mime_data) -> bool:
        return bool(self._video_paths_from_mime(mime_data))

    def _video_paths_from_mime(self, mime_data) -> list[Path]:
        if not mime_data.hasUrls():
            return []
        paths: list[Path] = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in self._VIDEO_EXTENSIONS:
                paths.append(path)
        return paths

    def add_video_paths(self, paths: list[Path]) -> None:
        existing = {self.item(row).data(Qt.UserRole) for row in range(self.count())}
        for path in paths:
            resolved = str(path.expanduser().resolve())
            if resolved in existing:
                continue
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, resolved)
            item.setToolTip(resolved)
            self.addItem(item)
            existing.add(resolved)

    def video_paths(self) -> list[str]:
        return [str(self.item(row).data(Qt.UserRole)) for row in range(self.count())]

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Waifu Desktop — Cola & Resultados")
        self.resize(1200, 750)
        self._dark_mode = True
        self._apply_theme()
        self._base_path: Path | None = None

        self.store = get_store()
        self.pack_service = PackService()
        self.dollimages_pack_service = DollimagesPackService()
        self.dollimages_manual_prompt_service = DollimagesManualPromptService()
        self.reel_service = ReelService()
        self.video_montage_service = VideoMontageService()
        self.manual_prompt_service = ManualPromptService()
        self.bulk_images_service = BulkImagesService()
        self.image2vid_service = ImageToVideoService()
        self.anime_generation_service = AnimeGenerationService()
        self.waifu_catalog = load_waifu_catalog()
        self.app_config = load_app_config()
        self.prompt_base_window: PromptBaseWindow | None = None
        self.prompt_variation_window: PromptVariationWindow | None = None
        self.social_copy_window: SocialCopyWindow | None = None
        self.dollimages_prompt_window: DollimagesPromptWindow | None = None
        self.video_prompt_template_window: VideoPromptTemplateWindow | None = None
        self.anime_v5_maintenance_window: AnimeV5MaintenanceWindow | None = None
        self.bulk_images_prompt_window: BulkImagesPromptWindow | None = None
        self.bulk_youtube_thread: BulkYoutubeVideoThread | None = None
        self.bulk_youtube_progress_dialog: QDialog | None = None

        # Mantener pixmaps originales para reescalar en resizeEvent
        self._pix_base: QPixmap | None = None
        self._preview_video_url: str | None = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._run_scheduled_refresh)
        self._preview_auto_disable_timer = QTimer(self)
        self._preview_auto_disable_timer.setSingleShot(True)
        self._preview_auto_disable_timer.timeout.connect(self._auto_disable_base_preview)
        self._refresh_resize_columns = False
        self._refresh_worker: RefreshWorker | None = None
        self._refresh_pending = False
        self._cached_filters: dict[str, list[str]] | None = None
        self._cached_status_counts: dict[str, int] | None = None
        self._cached_category_counts: list[tuple[str, int]] | None = None
        self._image2vid_source_options: list[dict[str, Any]] = []
        self._image2vid_filtered_source_options: list[dict[str, Any]] = []
        self._image2vid_prompt_templates: list[dict[str, Any]] = []

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        menu = self.menuBar()
        file_menu = menu.addMenu("Archivo")
        queue_menu = menu.addMenu("Cola")
        reel_menu = menu.addMenu("Reel")
        view_menu = menu.addMenu("Vista")
        maintenance_menu = menu.addMenu("Mantenimiento")
        self.open_base_action = file_menu.addAction("Abrir Base")
        self.open_up_action = file_menu.addAction("Abrir Upscale")
        self.open_folder_base_action = file_menu.addAction("Abrir Carpeta (Base)")
        self.open_folder_up_action = file_menu.addAction("Abrir Carpeta (Upscale)")
        self.open_video_action = file_menu.addAction("Abrir Video")
        self.open_folder_video_action = file_menu.addAction("Abrir Carpeta (Video)")
        file_menu.addSeparator()
        self.exit_action = file_menu.addAction("Salir")
        self.exit_action.triggered.connect(self.close)

        self.refresh_action = queue_menu.addAction("Refrescar")
        self.pause_action = queue_menu.addAction("Pausar cola")
        self.resume_action = queue_menu.addAction("Reanudar cola")
        queue_menu.addSeparator()
        self.clear_queued_action = queue_menu.addAction("Borrar estado QUEUED")
        self.refresh_action.setShortcut("F5")
        self.pause_action.setShortcut("Ctrl+Shift+P")
        self.resume_action.setShortcut("Ctrl+Shift+R")

        self.mark_reel_priority_action = reel_menu.addAction("Marcar prioridad reel")
        self.mark_reel_discard_action = reel_menu.addAction("Descartar en reels")
        reel_menu.addSeparator()
        self.clear_reel_flags_action = reel_menu.addAction("Limpiar marcas de reel")

        self.toggle_preview_action = view_menu.addAction("Mostrar preview")
        self.toggle_preview_action.setCheckable(True)
        self.toggle_preview_action.setChecked(False)
        self.toggle_worker_log_action = view_menu.addAction("Mostrar log del worker")
        self.toggle_worker_log_action.setCheckable(True)
        self.toggle_worker_log_action.setChecked(True)
        view_menu.addSeparator()
        self.toggle_dark_mode_action = view_menu.addAction("Modo oscuro")
        self.toggle_dark_mode_action.setCheckable(True)
        self.toggle_dark_mode_action.setChecked(self._dark_mode)
        self.toggle_dark_mode_action.triggered.connect(self._set_dark_mode)
        self.view_production_action = view_menu.addAction("Ver producción")
        self.view_production_action.triggered.connect(self.open_production_dialog)

        self.open_prompt_base_action = maintenance_menu.addAction("Categorías y personajes")
        self.open_prompt_base_action.triggered.connect(self.open_prompt_base_window)
        self.open_prompt_variation_action = maintenance_menu.addAction("Opciones y variaciones")
        self.open_prompt_variation_action.triggered.connect(self.open_prompt_variation_window)
        self.open_social_copy_action = maintenance_menu.addAction("Copys redes sociales")
        self.open_social_copy_action.triggered.connect(self.open_social_copy_window)
        self.open_dollimages_prompt_action = maintenance_menu.addAction("Prompts Dollimages")
        self.open_dollimages_prompt_action.triggered.connect(self.open_dollimages_prompt_window)
        self.open_video_prompt_templates_action = maintenance_menu.addAction("Prompts tipo video")
        self.open_video_prompt_templates_action.triggered.connect(self.open_video_prompt_template_window)
        self.open_anime_v5_maintenance_action = maintenance_menu.addAction("Anime V5: personajes y prompts")
        self.open_anime_v5_maintenance_action.triggered.connect(self.open_anime_v5_maintenance_window)
        self.open_bulk_images_prompt_action = maintenance_menu.addAction("Bulk Images: biblioteca de prompts")
        self.open_bulk_images_prompt_action.triggered.connect(self.open_bulk_images_prompt_window)
        maintenance_menu.addSeparator()
        self.clear_category_images_action = maintenance_menu.addAction("Vaciar imágenes por categoría")
        self.clear_category_images_action.triggered.connect(self.open_clear_category_images_dialog)

        header = QHBoxLayout()
        title_stack = QVBoxLayout()
        title_label = QLabel("Waifu Desktop")
        title_label.setObjectName("AppTitle")
        subtitle_label = QLabel("Panel comercial de producción, cola y resultados")
        subtitle_label.setObjectName("AppSubtitle")
        title_stack.addWidget(title_label)
        title_stack.addWidget(subtitle_label)
        header.addLayout(title_stack)
        header.addStretch(1)
        layout.addLayout(header)

        self.quick_actions_layout = QGridLayout()
        self.quick_actions_layout.setHorizontalSpacing(10)
        self.quick_actions_layout.setVerticalSpacing(8)
        self.open_filters_btn = QPushButton("Filtros inteligentes")
        self.open_pack_btn = QPushButton("Generar Pack Waifu")
        self.open_manual_prompt_btn = QPushButton("Prompt Manual Waifu")
        self.open_dollimages_pack_btn = QPushButton("Crear Pack Dollimages")
        self.open_dollimages_manual_prompt_btn = QPushButton("Prompt Manual Dollimages")
        self.open_image2vid_btn = QPushButton("Image2Vid WAN 2.2")
        self.open_undress_btn = QPushButton("Undress")
        self.open_anime_v5_btn = QPushButton("Anime V5")
        self.open_bulk_images_btn = QPushButton("Bulk Images")
        self.open_reel_btn = QPushButton("Reel Instagram")
        self.open_dollimages_reel_btn = QPushButton("Reel Dollimages")
        self.open_anime_v5_reel_btn = QPushButton("Reel Anime V5")
        self.open_video_montage_btn = QPushButton("Montar Videos")
        self.open_bulk_youtube_btn = QPushButton("YouTube Bulk")
        self.quick_action_buttons = (
            self.open_filters_btn,
            self.open_pack_btn,
            self.open_manual_prompt_btn,
            self.open_dollimages_pack_btn,
            self.open_dollimages_manual_prompt_btn,
            self.open_image2vid_btn,
            self.open_undress_btn,
            self.open_anime_v5_btn,
            self.open_bulk_images_btn,
            self.open_reel_btn,
            self.open_dollimages_reel_btn,
            self.open_anime_v5_reel_btn,
            self.open_video_montage_btn,
            self.open_bulk_youtube_btn,
        )
        for button in self.quick_action_buttons:
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._quick_actions_columns = 0
        layout.addLayout(self.quick_actions_layout)

        summary_group = QGroupBox("Resumen rápido")
        summary_group.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_group)
        self.status_total_label = QLabel("Total: 0")
        self.status_created_label = QLabel("CREATED: 0")
        self.status_queued_label = QLabel("QUEUED: 0")
        self.status_sent_label = QLabel("SENT: 0")
        self.status_done_label = QLabel("DONE: 0")
        self.status_failed_label = QLabel("FAILED: 0")
        self.status_eta_label = QLabel("Tiempo restante: —")
        summary_layout.addStretch(1)
        for lbl in (
            self.status_total_label,
            self.status_created_label,
            self.status_queued_label,
            self.status_sent_label,
            self.status_done_label,
            self.status_failed_label,
            self.status_eta_label,
        ):
            summary_layout.addWidget(lbl)
        summary_layout.addStretch(1)
        layout.addWidget(summary_group)

        operation_group = QGroupBox("Operación")
        operation_group.setObjectName("Card")
        self.operation_layout = QGridLayout(operation_group)
        self.start_worker_btn = QPushButton("Iniciar Worker")
        self.stop_worker_btn = QPushButton("Parar Worker")
        self.clear_queued_btn = QPushButton("Borrar QUEUED")
        self.clear_queued_btn.setToolTip("Elimina de la cola todos los prompts cuyo estado sea QUEUED.")
        self.stop_worker_btn.setEnabled(False)

        self.worker_status_label = QLabel("Worker: STOPPED")
        self.worker_status_label.setAlignment(Qt.AlignVCenter)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 500)
        self.limit_spin.setValue(200)

        self.pause_between_spin = QSpinBox()
        self.pause_between_spin.setRange(0, 60)
        self.pause_between_spin.setValue(5)
        self.pause_between_spin.setToolTip("Segundos de descanso entre imágenes procesadas.")

        self.preview_toggle_check = QCheckBox("Mostrar preview")
        self.preview_toggle_check.setChecked(False)

        self.preview_auto_disable_spin = QSpinBox()
        self.preview_auto_disable_spin.setRange(1, 3600)
        self.preview_auto_disable_spin.setValue(60)
        self.preview_auto_disable_spin.setToolTip(
            "Segundos que la vista previa permanecerá visible antes de desactivarse automáticamente."
        )

        self.operation_widgets = (
            self.start_worker_btn,
            self.stop_worker_btn,
            self.clear_queued_btn,
            self.worker_status_label,
            self._inline_operation_widget("Mostrar:", self.limit_spin),
            self._inline_operation_widget("Pausa (s):", self.pause_between_spin),
            self.preview_toggle_check,
            self._inline_operation_widget("Auto-ocultar preview (s):", self.preview_auto_disable_spin),
        )
        for widget in self.operation_widgets:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._operation_columns = 0
        layout.addWidget(operation_group)

        self.filters_dialog = QDialog(self)
        self.filters_dialog.setWindowTitle("Filtros inteligentes")
        self.filters_dialog.setModal(False)
        filters_dialog_layout = QVBoxLayout(self.filters_dialog)
        filters_group = QGroupBox("Filtros inteligentes")
        filters_layout = QGridLayout(filters_group)
        filters_layout.setHorizontalSpacing(10)
        filters_layout.setVerticalSpacing(8)

        filters_layout.addWidget(QLabel("Prompt ID:"), 0, 0)
        self.prompt_id_input = QLineEdit()
        self.prompt_id_input.setPlaceholderText("Buscar ID")
        self.prompt_id_input.setMaximumWidth(120)
        filters_layout.addWidget(self.prompt_id_input, 0, 1)

        filters_layout.addWidget(QLabel("Categoría:"), 0, 2)
        self.filter_category_combo = QComboBox()
        self.filter_category_combo.setMinimumWidth(130)
        filters_layout.addWidget(self.filter_category_combo, 0, 3)

        filters_layout.addWidget(QLabel("Versión:"), 0, 4)
        self.filter_variant_combo = QComboBox()
        self.filter_variant_combo.setMinimumWidth(130)
        filters_layout.addWidget(self.filter_variant_combo, 0, 5)

        filters_layout.addWidget(QLabel("Estado:"), 0, 6)
        self.filter_status_combo = QComboBox()
        self.filter_status_combo.setMinimumWidth(130)
        filters_layout.addWidget(self.filter_status_combo, 0, 7)

        filters_layout.addWidget(QLabel("Ratio:"), 1, 0)
        self.filter_ratio_combo = QComboBox()
        self.filter_ratio_combo.setMinimumWidth(110)
        filters_layout.addWidget(self.filter_ratio_combo, 1, 1)

        filters_layout.addWidget(QLabel("Últimos días:"), 1, 2)
        self.filter_last_days_spin = QSpinBox()
        self.filter_last_days_spin.setRange(1, 3650)
        self.filter_last_days_spin.setValue(30)
        self.filter_last_days_spin.setMinimumWidth(90)
        filters_layout.addWidget(self.filter_last_days_spin, 1, 3)

        self.filter_from_datetime = QDateTimeEdit()
        self.filter_from_datetime.setCalendarPopup(True)
        self.filter_from_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.filter_from_datetime.setMinimumDateTime(QDateTime(QDate(2000, 1, 1), QTime(0, 0, 0)))
        self.filter_from_datetime.setSpecialValueText("Desde")
        self.filter_from_datetime.setMinimumWidth(170)

        self.filter_to_datetime = QDateTimeEdit()
        self.filter_to_datetime.setCalendarPopup(True)
        self.filter_to_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.filter_to_datetime.setMinimumDateTime(QDateTime(QDate(2000, 1, 1), QTime(0, 0, 0)))
        self.filter_to_datetime.setSpecialValueText("Hasta")
        self.filter_to_datetime.setMinimumWidth(170)

        self._apply_last_days_range(self.filter_last_days_spin.value())

        self.reset_filters_btn = QPushButton("Restablecer filtros")
        filters_layout.addWidget(QLabel("Desde:"), 1, 4)
        filters_layout.addWidget(self.filter_from_datetime, 1, 5)
        filters_layout.addWidget(QLabel("Hasta:"), 1, 6)
        filters_layout.addWidget(self.filter_to_datetime, 1, 7)

        filters_layout.addWidget(QLabel("Orden fecha:"), 2, 0)
        self.filter_date_order_combo = QComboBox()
        self.filter_date_order_combo.addItem("Más recientes", "desc")
        self.filter_date_order_combo.addItem("Más antiguas", "asc")
        self.filter_date_order_combo.setMinimumWidth(150)
        filters_layout.addWidget(self.filter_date_order_combo, 2, 1)
        filters_layout.addWidget(QLabel("Checkpoint base:"), 2, 2)
        self.filter_checkpoint_base_combo = QComboBox()
        self.filter_checkpoint_base_combo.setMinimumWidth(220)
        filters_layout.addWidget(self.filter_checkpoint_base_combo, 2, 3, 1, 3)
        filters_layout.addWidget(self.reset_filters_btn, 2, 6, 1, 2)
        filters_layout.setColumnStretch(8, 1)
        filters_dialog_layout.addWidget(filters_group)

        # Pack generator
        self.pack_dialog = QDialog(self)
        self.pack_dialog.setWindowTitle("Generar Pack")
        self.pack_dialog.setModal(False)
        pack_dialog_layout = QVBoxLayout(self.pack_dialog)
        pack_group = QGroupBox("Generar Pack")
        pack_layout = QGridLayout(pack_group)
        pack_layout.setHorizontalSpacing(10)
        pack_layout.setVerticalSpacing(8)

        pack_layout.addWidget(QLabel("Categoría:"), 0, 0)
        self.pack_category_combo = QComboBox()
        pack_layout.addWidget(self.pack_category_combo, 0, 1)

        pack_layout.addWidget(QLabel("Variante:"), 0, 2)
        self.pack_variant_combo = QComboBox()
        pack_layout.addWidget(self.pack_variant_combo, 0, 3)

        pack_layout.addWidget(QLabel("Combinación:"), 0, 4)
        self.pack_combination_combo = QComboBox()
        pack_layout.addWidget(self.pack_combination_combo, 0, 5)

        pack_layout.addWidget(QLabel("Cantidad:"), 0, 6)
        self.pack_quantity_spin = QSpinBox()
        self.pack_quantity_spin.setRange(1, 500)
        self.pack_quantity_spin.setValue(10)
        pack_layout.addWidget(self.pack_quantity_spin, 0, 7)

        self.pack_nsfw_tag_label = QLabel("Etiquetas NSFW:")
        pack_layout.addWidget(self.pack_nsfw_tag_label, 1, 0)
        self.pack_nsfw_tag_spin = QSpinBox()
        self.pack_nsfw_tag_spin.setRange(1, 50)
        self.pack_nsfw_tag_spin.setValue(6)
        pack_layout.addWidget(self.pack_nsfw_tag_spin, 1, 1)

        pack_layout.addWidget(QLabel("Checkpoint Base:"), 1, 2)
        self.pack_checkpoint_base_combo = QComboBox()
        self.pack_checkpoint_base_combo.setMinimumWidth(220)
        pack_layout.addWidget(self.pack_checkpoint_base_combo, 1, 3)

        pack_layout.addWidget(QLabel("Checkpoint Refiner:"), 1, 4)
        self.pack_checkpoint_refiner_combo = QComboBox()
        self.pack_checkpoint_refiner_combo.setMinimumWidth(220)
        pack_layout.addWidget(self.pack_checkpoint_refiner_combo, 1, 5)

        self.pack_generate_btn = QPushButton("Generar Pack Waifu")
        pack_layout.addWidget(self.pack_generate_btn, 1, 6, 1, 2)
        pack_layout.setColumnStretch(8, 1)

        pack_layout.addWidget(QLabel("Característica extra:"), 2, 0)
        self.pack_manual_feature_input = QLineEdit()
        self.pack_manual_feature_input.setPlaceholderText("Añade una característica común para todo el pack")
        pack_layout.addWidget(self.pack_manual_feature_input, 2, 1, 1, 7)

        pack_dialog_layout.addWidget(pack_group)

        # Manual prompt generator
        self.manual_prompt_dialog = QDialog(self)
        self.manual_prompt_dialog.setWindowTitle("Prompt manual")
        self.manual_prompt_dialog.setModal(False)
        manual_dialog_layout = QVBoxLayout(self.manual_prompt_dialog)
        manual_group = QGroupBox("Prompt manual (Waifu)")
        manual_layout = QGridLayout(manual_group)
        manual_layout.setHorizontalSpacing(10)
        manual_layout.setVerticalSpacing(8)

        manual_layout.addWidget(QLabel("Categoría:"), 0, 0)
        self.manual_prompt_category_combo = QComboBox()
        manual_layout.addWidget(self.manual_prompt_category_combo, 0, 1)

        manual_layout.addWidget(QLabel("Variante:"), 0, 2)
        self.manual_prompt_variant_combo = QComboBox()
        manual_layout.addWidget(self.manual_prompt_variant_combo, 0, 3)

        manual_layout.addWidget(QLabel("Ratio:"), 0, 4)
        self.manual_prompt_ratio_combo = QComboBox()
        manual_layout.addWidget(self.manual_prompt_ratio_combo, 0, 5)

        manual_layout.addWidget(QLabel("Cantidad:"), 0, 6)
        self.manual_prompt_quantity_spin = QSpinBox()
        self.manual_prompt_quantity_spin.setRange(1, 200)
        self.manual_prompt_quantity_spin.setValue(1)
        manual_layout.addWidget(self.manual_prompt_quantity_spin, 0, 7)

        manual_layout.addWidget(QLabel("Checkpoint Base:"), 1, 0)
        self.manual_prompt_checkpoint_combo = QComboBox()
        self.manual_prompt_checkpoint_combo.setMinimumWidth(220)
        manual_layout.addWidget(self.manual_prompt_checkpoint_combo, 1, 1, 1, 3)

        manual_layout.addWidget(QLabel("Refiner:"), 1, 4)
        self.manual_prompt_refiner_label = QLabel("—")
        manual_layout.addWidget(self.manual_prompt_refiner_label, 1, 5, 1, 3)

        manual_layout.addWidget(QLabel("Título:"), 2, 0)
        self.manual_prompt_title_input = QLineEdit()
        self.manual_prompt_title_input.setPlaceholderText("Título manual")
        manual_layout.addWidget(self.manual_prompt_title_input, 2, 1, 1, 7)

        manual_layout.addWidget(QLabel("Prompt manual:"), 3, 0)
        self.manual_prompt_text_input = QPlainTextEdit()
        self.manual_prompt_text_input.setPlaceholderText("Escribe el prompt tal cual lo quieres enviar.")
        self.manual_prompt_text_input.setMinimumHeight(140)
        manual_layout.addWidget(self.manual_prompt_text_input, 3, 1, 1, 7)

        self.manual_prompt_generate_btn = QPushButton("Enviar a cola")
        manual_layout.addWidget(self.manual_prompt_generate_btn, 4, 6, 1, 2)
        manual_layout.setColumnStretch(8, 1)

        manual_dialog_layout.addWidget(manual_group)

        # Dollimages pack generator
        self.dollimages_dialog = QDialog(self)
        self.dollimages_dialog.setWindowTitle("Crear Pack Dollimages")
        self.dollimages_dialog.setModal(False)
        doll_dialog_layout = QVBoxLayout(self.dollimages_dialog)
        doll_group = QGroupBox("Crear Pack Dollimages")
        doll_layout = QGridLayout(doll_group)
        doll_layout.setHorizontalSpacing(10)
        doll_layout.setVerticalSpacing(8)

        doll_layout.addWidget(QLabel("Tipología:"), 0, 0)
        self.dollimages_typology_combo = QComboBox()
        self.dollimages_typology_combo.addItem("Normal", "normal")
        self.dollimages_typology_combo.addItem("SFW", "sfw")
        self.dollimages_typology_combo.addItem("NSFW", "nsfw")
        doll_layout.addWidget(self.dollimages_typology_combo, 0, 1)

        doll_layout.addWidget(QLabel("Imagen referencia:"), 0, 2)
        self.dollimages_reference_input = QLineEdit()
        self.dollimages_reference_input.setPlaceholderText("Selecciona una imagen para faceswap")
        doll_layout.addWidget(self.dollimages_reference_input, 0, 3, 1, 3)
        self.dollimages_reference_btn = QPushButton("Buscar")
        doll_layout.addWidget(self.dollimages_reference_btn, 0, 6)
        self.dollimages_faceswap_check = QCheckBox("Faceswap")
        self.dollimages_faceswap_check.setChecked(True)
        doll_layout.addWidget(self.dollimages_faceswap_check, 0, 7)

        doll_layout.addWidget(QLabel("Checkpoint Base:"), 1, 0)
        self.dollimages_checkpoint_combo = QComboBox()
        self.dollimages_checkpoint_combo.setMinimumWidth(220)
        doll_layout.addWidget(self.dollimages_checkpoint_combo, 1, 1)

        doll_layout.addWidget(QLabel("Iteraciones por prompt:"), 1, 2)
        self.dollimages_iterations_spin = QSpinBox()
        self.dollimages_iterations_spin.setRange(1, 500)
        self.dollimages_iterations_spin.setValue(1)
        doll_layout.addWidget(self.dollimages_iterations_spin, 1, 3)

        doll_layout.addWidget(QLabel("Grupo:"), 1, 4)
        self.dollimages_group_combo = QComboBox()
        self.dollimages_group_combo.setMinimumWidth(180)
        doll_layout.addWidget(self.dollimages_group_combo, 1, 5)

        doll_layout.addWidget(QLabel("Workflow:"), 1, 6)
        self.dollimages_workflow_combo = QComboBox()
        self.dollimages_workflow_combo.addItem("Dollimages", "dollimages")
        self.dollimages_workflow_combo.addItem("Dollimages Z", "dollimagesz")
        self.dollimages_workflow_combo.addItem("Krea2", "krea2")
        doll_layout.addWidget(self.dollimages_workflow_combo, 1, 7)

        doll_layout.addWidget(QLabel("Ratio:"), 2, 6)
        self.dollimages_ratio_combo = QComboBox()
        for label in ("1:1", "9:16", "16:9", "3:4", "4:3"):
            self.dollimages_ratio_combo.addItem(label, label)
        self.dollimages_ratio_combo.setCurrentText("3:4")
        doll_layout.addWidget(self.dollimages_ratio_combo, 2, 7)

        doll_layout.addWidget(QLabel("Texto manual:"), 2, 0)
        self.dollimages_manual_input = QLineEdit()
        self.dollimages_manual_input.setPlaceholderText("Añade un texto común para todo el pack")
        doll_layout.addWidget(self.dollimages_manual_input, 2, 1, 1, 5)

        self.dollimages_generate_btn = QPushButton("Crear Pack Dollimages")
        doll_layout.addWidget(self.dollimages_generate_btn, 3, 6)
        doll_layout.setColumnStretch(7, 1)

        doll_dialog_layout.addWidget(doll_group)

        # Dollimages manual prompt generator
        self.dollimages_manual_dialog = QDialog(self)
        self.dollimages_manual_dialog.setWindowTitle("Prompt manual Dollimages")
        self.dollimages_manual_dialog.setModal(False)
        doll_manual_layout = QVBoxLayout(self.dollimages_manual_dialog)
        doll_manual_group = QGroupBox("Prompt manual (Dollimages)")
        doll_manual_grid = QGridLayout(doll_manual_group)
        doll_manual_grid.setHorizontalSpacing(10)
        doll_manual_grid.setVerticalSpacing(8)

        doll_manual_grid.addWidget(QLabel("Tipología:"), 0, 0)
        self.dollimages_manual_typology_combo = QComboBox()
        self.dollimages_manual_typology_combo.addItem("Normal", "normal")
        self.dollimages_manual_typology_combo.addItem("SFW", "sfw")
        self.dollimages_manual_typology_combo.addItem("NSFW", "nsfw")
        doll_manual_grid.addWidget(self.dollimages_manual_typology_combo, 0, 1)

        doll_manual_grid.addWidget(QLabel("Imagen referencia:"), 0, 2)
        self.dollimages_manual_reference_input = QLineEdit()
        self.dollimages_manual_reference_input.setPlaceholderText("Selecciona una imagen para faceswap")
        doll_manual_grid.addWidget(self.dollimages_manual_reference_input, 0, 3, 1, 3)
        self.dollimages_manual_reference_btn = QPushButton("Buscar")
        doll_manual_grid.addWidget(self.dollimages_manual_reference_btn, 0, 6)
        self.dollimages_manual_faceswap_check = QCheckBox("Faceswap")
        self.dollimages_manual_faceswap_check.setChecked(True)
        doll_manual_grid.addWidget(self.dollimages_manual_faceswap_check, 0, 7)

        doll_manual_grid.addWidget(QLabel("Checkpoint Base:"), 1, 0)
        self.dollimages_manual_checkpoint_combo = QComboBox()
        self.dollimages_manual_checkpoint_combo.setMinimumWidth(220)
        doll_manual_grid.addWidget(self.dollimages_manual_checkpoint_combo, 1, 1)

        doll_manual_grid.addWidget(QLabel("Repeticiones:"), 1, 2)
        self.dollimages_manual_repetitions_spin = QSpinBox()
        self.dollimages_manual_repetitions_spin.setRange(1, 500)
        self.dollimages_manual_repetitions_spin.setValue(1)
        doll_manual_grid.addWidget(self.dollimages_manual_repetitions_spin, 1, 3)

        doll_manual_grid.addWidget(QLabel("Workflow:"), 1, 4)
        self.dollimages_manual_workflow_combo = QComboBox()
        self.dollimages_manual_workflow_combo.addItem("Dollimages", "dollimages")
        self.dollimages_manual_workflow_combo.addItem("Dollimages Z", "dollimagesz")
        self.dollimages_manual_workflow_combo.addItem("Krea2", "krea2")
        doll_manual_grid.addWidget(self.dollimages_manual_workflow_combo, 1, 5)

        doll_manual_grid.addWidget(QLabel("Ratio:"), 1, 6)
        self.dollimages_manual_ratio_combo = QComboBox()
        for label in ("1:1", "9:16", "16:9", "3:4", "4:3"):
            self.dollimages_manual_ratio_combo.addItem(label, label)
        self.dollimages_manual_ratio_combo.setCurrentText("3:4")
        doll_manual_grid.addWidget(self.dollimages_manual_ratio_combo, 1, 7)

        doll_manual_grid.addWidget(QLabel("Título:"), 2, 0)
        self.dollimages_manual_title_input = QLineEdit()
        self.dollimages_manual_title_input.setPlaceholderText("Título manual")
        doll_manual_grid.addWidget(self.dollimages_manual_title_input, 2, 1, 1, 6)

        doll_manual_grid.addWidget(QLabel("Prompt manual:"), 3, 0)
        self.dollimages_manual_prompt_text_input = QPlainTextEdit()
        self.dollimages_manual_prompt_text_input.setPlaceholderText("Escribe el prompt tal cual lo quieres enviar.")
        self.dollimages_manual_prompt_text_input.setMinimumHeight(120)
        doll_manual_grid.addWidget(self.dollimages_manual_prompt_text_input, 3, 1, 1, 6)

        self.dollimages_manual_generate_btn = QPushButton("Enviar a cola")
        doll_manual_grid.addWidget(self.dollimages_manual_generate_btn, 4, 6)

        # Anime V5 generator
        self.anime_v5_dialog = QDialog(self)
        self.anime_v5_dialog.setWindowTitle("Generar Anime V5")
        self.anime_v5_dialog.setModal(False)
        self.anime_v5_dialog.resize(1040, 760)
        self.anime_v5_dialog.setMinimumSize(920, 680)
        anime_layout = QVBoxLayout(self.anime_v5_dialog)
        anime_group = QGroupBox("Prompt reutilizable por personaje (anime-v5.json)")
        anime_grid = QGridLayout(anime_group)
        anime_grid.addWidget(QLabel("Lista:"), 0, 0)
        self.anime_v5_list_combo = QComboBox()
        self.anime_v5_list_combo.setEditable(True)
        self.anime_v5_list_combo.setMinimumWidth(220)
        self.anime_v5_list_combo.setPlaceholderText("Ej: Personajes Dragon Ball")
        anime_grid.addWidget(self.anime_v5_list_combo, 0, 1, 1, 2)
        self.anime_v5_list_selection = QListWidget()
        self.anime_v5_list_selection.setSelectionMode(QAbstractItemView.MultiSelection)
        self.anime_v5_list_selection.setMinimumWidth(220)
        self.anime_v5_list_selection.setMaximumHeight(130)
        self.anime_v5_list_selection.setToolTip("Selecciona una o varias listas antes de generar. Si no seleccionas ninguna, se usará la lista activa.")
        anime_grid.addWidget(self.anime_v5_list_selection, 1, 1, 2, 2)
        self.anime_v5_select_all_lists_btn = QPushButton("Todas")
        anime_grid.addWidget(self.anime_v5_select_all_lists_btn, 1, 3)
        self.anime_v5_clear_lists_btn = QPushButton("Limpiar")
        anime_grid.addWidget(self.anime_v5_clear_lists_btn, 2, 3)
        self.anime_v5_maintenance_btn = QPushButton("Mantenimiento...")
        anime_grid.addWidget(self.anime_v5_maintenance_btn, 0, 3)
        anime_grid.addWidget(QLabel("Clasificación:"), 0, 4)
        self.anime_v5_content_rating_combo = QComboBox()
        self.anime_v5_content_rating_combo.addItem("SFW", "sfw")
        self.anime_v5_content_rating_combo.addItem("NSFW", "nsfw")
        anime_grid.addWidget(self.anime_v5_content_rating_combo, 0, 5)
        anime_grid.addWidget(QLabel("Imágenes por personaje:"), 1, 4)
        self.anime_v5_quantity_spin = QSpinBox()
        self.anime_v5_quantity_spin.setRange(1, 500)
        self.anime_v5_quantity_spin.setValue(1)
        anime_grid.addWidget(self.anime_v5_quantity_spin, 1, 5)
        anime_grid.addWidget(QLabel("Personaje concreto:"), 2, 4)
        self.anime_v5_single_character_combo = QComboBox()
        self.anime_v5_single_character_combo.addItem("Todos", None)
        self.anime_v5_single_character_combo.setToolTip("Opcional: genera solo un personaje cuando hay una única lista seleccionada o activa.")
        anime_grid.addWidget(self.anime_v5_single_character_combo, 2, 5)
        anime_grid.addWidget(QLabel("Listas a generar:"), 1, 0)
        anime_grid.addWidget(QLabel("Título prompt:"), 3, 0)
        self.anime_v5_prompt_title_input = QLineEdit()
        self.anime_v5_prompt_title_input.setPlaceholderText("Ej: Traje elegante penthouse")
        anime_grid.addWidget(self.anime_v5_prompt_title_input, 3, 1, 1, 4)
        self.anime_v5_pick_prompt_btn = QPushButton("Buscar prompt...")
        anime_grid.addWidget(self.anime_v5_pick_prompt_btn, 3, 5)
        anime_grid.addWidget(QLabel("Outfit fijo:"), 4, 0)
        self.anime_v5_fixed_outfit_combo = QComboBox()
        self.anime_v5_fixed_outfit_combo.setEditable(True)
        self.anime_v5_fixed_outfit_combo.setPlaceholderText("Aleatorio")
        anime_grid.addWidget(self.anime_v5_fixed_outfit_combo, 4, 1, 1, 4)
        self.anime_v5_generator_btn = QPushButton("Generador Anime V5")
        self.anime_v5_generator_btn.setMinimumWidth(140)
        anime_grid.addWidget(self.anime_v5_generator_btn, 4, 5)
        anime_grid.addWidget(QLabel("Combinaciones aleatorias:"), 5, 0)
        self.anime_v5_random_combinations_spin = QSpinBox()
        self.anime_v5_random_combinations_spin.setRange(1, 500)
        self.anime_v5_random_combinations_spin.setValue(1)
        self.anime_v5_random_combinations_spin.setToolTip(
            "Genera esta cantidad de combinaciones aleatorias del generador Anime V5 y encola las imágenes por personaje para cada una."
        )
        anime_grid.addWidget(self.anime_v5_random_combinations_spin, 5, 1)
        anime_grid.addWidget(QLabel("Texto extra outfit:"), 5, 2)
        self.anime_v5_manual_outfit_input = QLineEdit()
        self.anime_v5_manual_outfit_input.setPlaceholderText("Opcional: se añade al outfit antes de generar el prompt")
        anime_grid.addWidget(self.anime_v5_manual_outfit_input, 5, 3, 1, 3)
        self.anime_v5_upskirt_on_skirt_checkbox = QCheckBox("Añadir upskirt si hay skirt")
        self.anime_v5_upskirt_on_skirt_checkbox.setToolTip(
            "Cuando esté activo, añade el texto 'upskirt' al prompt final si la combinación contiene 'skirt'."
        )
        anime_grid.addWidget(self.anime_v5_upskirt_on_skirt_checkbox, 6, 1, 1, 5)
        anime_grid.addWidget(QLabel("Modelo principal:"), 7, 0)
        self.anime_v5_checkpoint_base_combo = QComboBox()
        self.anime_v5_checkpoint_base_combo.setMinimumWidth(220)
        anime_grid.addWidget(self.anime_v5_checkpoint_base_combo, 7, 1, 1, 2)
        anime_grid.addWidget(QLabel("Modelo refined:"), 7, 3)
        self.anime_v5_checkpoint_refiner_combo = QComboBox()
        self.anime_v5_checkpoint_refiner_combo.setMinimumWidth(220)
        anime_grid.addWidget(self.anime_v5_checkpoint_refiner_combo, 7, 4, 1, 2)
        anime_grid.addWidget(QLabel("Personajes:"), 8, 0)
        self.anime_v5_characters_input = QPlainTextEdit()
        self.anime_v5_characters_input.setPlaceholderText(
            'Un personaje por línea o JSON. Ej:\n'
            '{"name": "Nami", "anime": "One Piece", "description": "beautiful anime woman with long bright orange hair, large brown eyes, slim curvy figure, recognizable anime-inspired appearance"}'
        )
        self.anime_v5_characters_input.setMinimumHeight(280)
        anime_grid.addWidget(self.anime_v5_characters_input, 8, 1, 1, 4)
        anime_grid.addWidget(QLabel("Prompt:"), 9, 0)
        self.anime_v5_prompt_input = QPlainTextEdit()
        self.anime_v5_prompt_input.setPlaceholderText("Usa [personaje], [anime], [description] y opcionalmente [shot], [pose], [location], [fit], [outfit], [fabric], [condition], [styling], [expression], [lighting].")
        self.anime_v5_prompt_input.setMinimumHeight(180)
        anime_grid.addWidget(self.anime_v5_prompt_input, 9, 1, 1, 5)
        anime_grid.setColumnStretch(1, 1)
        anime_grid.setRowStretch(8, 3)
        anime_grid.setRowStretch(9, 2)
        self.anime_v5_options_label = QLabel(f"Opciones editables: {DEFAULT_OPTIONS_PATH}")
        self.anime_v5_options_label.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        anime_grid.addWidget(self.anime_v5_options_label, 10, 1, 1, 3)
        self.anime_v5_generate_btn = QPushButton("Crear imágenes Anime V5")
        anime_grid.addWidget(self.anime_v5_generate_btn, 10, 4, 1, 2)
        anime_layout.addWidget(anime_group)

        self.anime_v5_prompt_picker_dialog = QDialog(self)
        self.anime_v5_prompt_picker_dialog.setWindowTitle("Seleccionar prompt Anime V5")
        self.anime_v5_prompt_picker_dialog.setModal(True)
        self.anime_v5_prompt_picker_dialog.resize(920, 560)
        anime_prompt_picker_layout = QVBoxLayout(self.anime_v5_prompt_picker_dialog)
        anime_prompt_filter_row = QHBoxLayout()
        anime_prompt_filter_row.addWidget(QLabel("Buscar:"))
        self.anime_v5_prompt_search_input = QLineEdit()
        self.anime_v5_prompt_search_input.setPlaceholderText("Filtrar por título o prompt")
        anime_prompt_filter_row.addWidget(self.anime_v5_prompt_search_input)
        anime_prompt_filter_row.addWidget(QLabel("Total:"))
        self.anime_v5_prompt_count_label = QLabel("0")
        anime_prompt_filter_row.addWidget(self.anime_v5_prompt_count_label)
        anime_prompt_picker_layout.addLayout(anime_prompt_filter_row)
        self.anime_v5_prompt_table = QTableWidget(0, 2)
        self.anime_v5_prompt_table.setHorizontalHeaderLabels(["Título", "Prompt"])
        self.anime_v5_prompt_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.anime_v5_prompt_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.anime_v5_prompt_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.anime_v5_prompt_table.verticalHeader().setVisible(False)
        anime_prompt_header = self.anime_v5_prompt_table.horizontalHeader()
        anime_prompt_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        anime_prompt_header.setSectionResizeMode(1, QHeaderView.Stretch)
        anime_prompt_picker_layout.addWidget(self.anime_v5_prompt_table, 1)
        anime_prompt_actions = QHBoxLayout()
        anime_prompt_actions.addStretch(1)
        self.anime_v5_prompt_cancel_btn = QPushButton("Cancelar")
        self.anime_v5_prompt_apply_btn = QPushButton("Usar prompt")
        anime_prompt_actions.addWidget(self.anime_v5_prompt_cancel_btn)
        anime_prompt_actions.addWidget(self.anime_v5_prompt_apply_btn)
        anime_prompt_picker_layout.addLayout(anime_prompt_actions)
        self._anime_v5_prompt_templates: list[dict[str, object]] = []

        doll_manual_grid.setColumnStretch(7, 1)

        doll_manual_layout.addWidget(doll_manual_group)

        self.image2vid_dialog = QDialog(self)
        self.image2vid_dialog.setWindowTitle("Image2Vid WAN 2.2")
        self.image2vid_dialog.setModal(False)
        image2vid_dialog_layout = QVBoxLayout(self.image2vid_dialog)
        image2vid_group = QGroupBox("Generar video desde la imagen seleccionada")
        image2vid_layout = QGridLayout(image2vid_group)
        image2vid_layout.setHorizontalSpacing(10)
        image2vid_layout.setVerticalSpacing(8)

        image2vid_layout.addWidget(QLabel("Imagen origen:"), 0, 0)
        self.image2vid_selected_source: dict[str, Any] | None = None
        self.image2vid_source_label = QLabel("Sin imagen seleccionada")
        self.image2vid_source_label.setStyleSheet("color: #9aa0a6;")
        image2vid_layout.addWidget(self.image2vid_source_label, 0, 1, 1, 4)
        self.image2vid_select_source_btn = QPushButton("Usar selección actual")
        image2vid_layout.addWidget(self.image2vid_select_source_btn, 0, 5)
        self.image2vid_reload_sources_btn = QPushButton("Actualizar")
        image2vid_layout.addWidget(self.image2vid_reload_sources_btn, 0, 6)

        image2vid_layout.addWidget(QLabel("Ratio:"), 1, 0)
        self.image2vid_ratio_combo = QComboBox()
        self.image2vid_ratio_combo.addItem("1:1", "1:1")
        self.image2vid_ratio_combo.addItem("4:5", "4:5")
        self.image2vid_ratio_combo.addItem("9:16", "9:16")
        self.image2vid_ratio_combo.addItem("16:9", "16:9")
        image2vid_layout.addWidget(self.image2vid_ratio_combo, 1, 1)

        image2vid_layout.addWidget(QLabel("Segundos:"), 1, 2)
        self.image2vid_seconds_spin = QDoubleSpinBox()
        self.image2vid_seconds_spin.setRange(1.0, 20.0)
        self.image2vid_seconds_spin.setSingleStep(0.5)
        self.image2vid_seconds_spin.setValue(5.0)
        image2vid_layout.addWidget(self.image2vid_seconds_spin, 1, 3)

        self.image2vid_size_label = QLabel("Tamaño: 720x720")
        self.image2vid_frames_label = QLabel("Frames Wan: 80")
        image2vid_layout.addWidget(self.image2vid_size_label, 1, 4)
        image2vid_layout.addWidget(self.image2vid_frames_label, 1, 5, 1, 2)

        image2vid_layout.addWidget(QLabel("Título:"), 2, 0)
        self.image2vid_title_input = QLineEdit()
        self.image2vid_title_input.setPlaceholderText("Título del video")
        image2vid_layout.addWidget(self.image2vid_title_input, 2, 1, 1, 6)

        image2vid_layout.addWidget(QLabel("Prompt +:"), 3, 0)
        self.image2vid_positive_input = QPlainTextEdit()
        self.image2vid_positive_input.setPlaceholderText("Prompt positivo")
        self.image2vid_positive_input.setFixedHeight(90)
        image2vid_layout.addWidget(self.image2vid_positive_input, 3, 1, 1, 5)
        self.image2vid_pick_prompt_btn = QPushButton("Usar prompt tipo...")
        image2vid_layout.addWidget(self.image2vid_pick_prompt_btn, 3, 6)

        image2vid_layout.addWidget(QLabel("Prompt -:"), 4, 0)
        self.image2vid_negative_input = QPlainTextEdit()
        self.image2vid_negative_input.setPlaceholderText("Prompt negativo")
        self.image2vid_negative_input.setPlainText(IMAGE2VID_MIN_NEGATIVE_PROMPT)
        self.image2vid_negative_input.setFixedHeight(90)
        image2vid_layout.addWidget(self.image2vid_negative_input, 4, 1, 1, 6)

        self.image2vid_generate_btn = QPushButton("Enviar Image2Vid a cola")
        image2vid_layout.addWidget(self.image2vid_generate_btn, 5, 5, 1, 2)

        image2vid_dialog_layout.addWidget(image2vid_group)

        self.undress_dialog = QDialog(self)
        self.undress_dialog.setWindowTitle("Undress")
        self.undress_dialog.setModal(False)
        undress_dialog_layout = QVBoxLayout(self.undress_dialog)
        undress_group = QGroupBox("Generar vídeo Undress desde una imagen de la cola")
        undress_layout = QGridLayout(undress_group)
        undress_layout.addWidget(QLabel("Imagen origen:"), 0, 0)
        self.undress_source_label = QLabel("Sin imagen seleccionada")
        self.undress_source_label.setStyleSheet("color: #9aa0a6;")
        undress_layout.addWidget(self.undress_source_label, 0, 1, 1, 3)
        self.undress_select_source_btn = QPushButton("Usar selección actual")
        undress_layout.addWidget(self.undress_select_source_btn, 0, 4)
        undress_layout.addWidget(QLabel("Prendas:"), 1, 0, Qt.AlignTop)
        self.undress_garment_list = QListWidget()
        self.undress_garment_list.setFixedHeight(150)
        for index, garment in enumerate(UNDRESS_GARMENTS):
            item = QListWidgetItem(garment)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if index == 0 else Qt.Unchecked)
            self.undress_garment_list.addItem(item)
        undress_layout.addWidget(self.undress_garment_list, 1, 1)
        self.undress_format_label = QLabel()
        undress_layout.addWidget(self.undress_format_label, 1, 2, 1, 3)
        undress_layout.addWidget(QLabel("Prompt fijo:"), 2, 0)
        self.undress_prompt_preview = QPlainTextEdit()
        self.undress_prompt_preview.setReadOnly(True)
        self.undress_prompt_preview.setFixedHeight(110)
        undress_layout.addWidget(self.undress_prompt_preview, 2, 1, 1, 4)
        self.undress_generate_btn = QPushButton("Enviar Undress a cola")
        undress_layout.addWidget(self.undress_generate_btn, 3, 3, 1, 2)
        undress_dialog_layout.addWidget(undress_group)
        self._update_undress_prompt()

        self.image2vid_source_picker_dialog = QDialog(self)
        self.image2vid_source_picker_dialog.setWindowTitle("Seleccionar imagen origen")
        self.image2vid_source_picker_dialog.setModal(True)
        self.image2vid_source_picker_dialog.resize(1160, 720)
        source_picker_layout = QVBoxLayout(self.image2vid_source_picker_dialog)
        source_picker_top = QHBoxLayout()
        source_picker_top.addWidget(QLabel("Imágenes disponibles (últimas 300):"))
        source_picker_top.addStretch(1)
        self.image2vid_source_count_label = QLabel("0")
        source_picker_top.addWidget(self.image2vid_source_count_label)
        source_picker_layout.addLayout(source_picker_top)

        source_picker_filters = QHBoxLayout()
        source_picker_filters.addWidget(QLabel("Categoría:"))
        self.image2vid_filter_category_combo = QComboBox()
        self.image2vid_filter_category_combo.addItem("Todas", None)
        source_picker_filters.addWidget(self.image2vid_filter_category_combo)
        source_picker_filters.addWidget(QLabel("Variante:"))
        self.image2vid_filter_variant_combo = QComboBox()
        self.image2vid_filter_variant_combo.addItem("Todas", None)
        source_picker_filters.addWidget(self.image2vid_filter_variant_combo)
        source_picker_filters.addStretch(1)
        source_picker_layout.addLayout(source_picker_filters)

        source_picker_content = QHBoxLayout()
        self.image2vid_source_table = QTableWidget(0, 3)
        self.image2vid_source_table.setHorizontalHeaderLabels(["ID", "Origen", "Título"])
        self.image2vid_source_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.image2vid_source_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.image2vid_source_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.image2vid_source_table.verticalHeader().setVisible(False)
        table_header = self.image2vid_source_table.horizontalHeader()
        table_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table_header.setSectionResizeMode(2, QHeaderView.Stretch)
        source_picker_content.addWidget(self.image2vid_source_table, 6)

        preview_panel = QVBoxLayout()
        preview_panel.addWidget(QLabel("Vista previa:"))
        self.image2vid_source_preview = QLabel("Selecciona una imagen")
        self.image2vid_source_preview.setAlignment(Qt.AlignCenter)
        self.image2vid_source_preview.setMinimumSize(420, 560)
        self.image2vid_source_preview.setStyleSheet("border: 1px solid #2b2f35; background: #14171c; color: #9aa0a6;")
        preview_panel.addWidget(self.image2vid_source_preview, 1)
        source_picker_content.addLayout(preview_panel, 4)
        source_picker_layout.addLayout(source_picker_content, 1)

        source_picker_actions = QHBoxLayout()
        source_picker_actions.addStretch(1)
        self.image2vid_source_cancel_btn = QPushButton("Cancelar")
        self.image2vid_source_apply_btn = QPushButton("Usar esta imagen")
        source_picker_actions.addWidget(self.image2vid_source_cancel_btn)
        source_picker_actions.addWidget(self.image2vid_source_apply_btn)
        source_picker_layout.addLayout(source_picker_actions)

        self.image2vid_prompt_picker_dialog = QDialog(self)
        self.image2vid_prompt_picker_dialog.setWindowTitle("Seleccionar prompt tipo para video")
        self.image2vid_prompt_picker_dialog.setModal(True)
        self.image2vid_prompt_picker_dialog.resize(980, 620)
        prompt_picker_layout = QVBoxLayout(self.image2vid_prompt_picker_dialog)

        prompt_filter_row = QHBoxLayout()
        prompt_filter_row.addWidget(QLabel("Buscar:"))
        self.image2vid_prompt_search_input = QLineEdit()
        self.image2vid_prompt_search_input.setPlaceholderText("Filtrar por título o texto del prompt")
        prompt_filter_row.addWidget(self.image2vid_prompt_search_input)
        prompt_filter_row.addWidget(QLabel("Total:"))
        self.image2vid_prompt_count_label = QLabel("0")
        prompt_filter_row.addWidget(self.image2vid_prompt_count_label)
        prompt_filter_row.addStretch(1)
        prompt_picker_layout.addLayout(prompt_filter_row)

        self.image2vid_prompt_table = QTableWidget(0, 2)
        self.image2vid_prompt_table.setHorizontalHeaderLabels(["Título", "Prompt tipo"])
        self.image2vid_prompt_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.image2vid_prompt_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.image2vid_prompt_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.image2vid_prompt_table.verticalHeader().setVisible(False)
        prompt_header = self.image2vid_prompt_table.horizontalHeader()
        prompt_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        prompt_header.setSectionResizeMode(1, QHeaderView.Stretch)
        prompt_picker_layout.addWidget(self.image2vid_prompt_table, 1)

        prompt_picker_actions = QHBoxLayout()
        prompt_picker_actions.addStretch(1)
        self.image2vid_prompt_cancel_btn = QPushButton("Cancelar")
        self.image2vid_prompt_apply_btn = QPushButton("Usar prompt")
        prompt_picker_actions.addWidget(self.image2vid_prompt_cancel_btn)
        prompt_picker_actions.addWidget(self.image2vid_prompt_apply_btn)
        prompt_picker_layout.addLayout(prompt_picker_actions)

        self.reel_dialog = QDialog(self)
        self.reel_dialog.setWindowTitle("Reel Instagram")
        self.reel_dialog.setModal(False)
        reel_dialog_layout = QVBoxLayout(self.reel_dialog)
        reel_group = QGroupBox("Reel Instagram")
        reel_layout = QGridLayout(reel_group)
        reel_layout.setHorizontalSpacing(10)
        reel_layout.setVerticalSpacing(8)

        reel_layout.addWidget(QLabel("Categoría:"), 0, 0)
        self.reel_category_combo = QComboBox()
        reel_layout.addWidget(self.reel_category_combo, 0, 1)

        reel_layout.addWidget(QLabel("Variante:"), 0, 2)
        self.reel_variant_combo = QComboBox()
        self.reel_variant_combo.setMinimumWidth(130)
        reel_layout.addWidget(self.reel_variant_combo, 0, 3)

        reel_layout.addWidget(QLabel("Cantidad imágenes:"), 0, 4)
        self.reel_quantity_spin = QSpinBox()
        self.reel_quantity_spin.setRange(1, 30)
        self.reel_quantity_spin.setValue(5)
        reel_layout.addWidget(self.reel_quantity_spin, 0, 5)

        reel_layout.addWidget(QLabel("Segundos por imagen:"), 0, 6)
        self.reel_seconds_spin = QDoubleSpinBox()
        self.reel_seconds_spin.setRange(1.0, 10.0)
        self.reel_seconds_spin.setSingleStep(0.5)
        self.reel_seconds_spin.setValue(2.0)
        reel_layout.addWidget(self.reel_seconds_spin, 0, 7)

        reel_layout.addWidget(QLabel("Redes (manual):"), 1, 0)
        self.reel_social_input = QLineEdit()
        self.reel_social_input.setPlaceholderText("Ej: @waifu / @instagram")
        reel_layout.addWidget(self.reel_social_input, 1, 1, 1, 4)
        reel_layout.addWidget(QLabel("Fundido final:"), 1, 5)
        self.reel_fade_out_checkbox = QCheckBox()
        self.reel_fade_out_checkbox.setChecked(True)
        reel_layout.addWidget(self.reel_fade_out_checkbox, 1, 6)

        self.reel_generate_btn = QPushButton("Crear Reel")
        reel_layout.addWidget(self.reel_generate_btn, 0, 8)
        reel_layout.setColumnStretch(9, 1)

        reel_dialog_layout.addWidget(reel_group)

        self.video_montage_dialog = QDialog(self)
        self.video_montage_dialog.setWindowTitle("Montar Videos")
        self.video_montage_dialog.setModal(False)
        self.video_montage_dialog.resize(760, 460)
        video_montage_layout = QVBoxLayout(self.video_montage_dialog)
        video_montage_group = QGroupBox("Concatenar vídeos con fundido y música aleatoria")
        video_montage_grid = QGridLayout(video_montage_group)
        video_montage_grid.setHorizontalSpacing(10)
        video_montage_grid.setVerticalSpacing(8)

        video_montage_grid.addWidget(QLabel("Vídeos:"), 0, 0)
        self.video_montage_list = VideoDropList()
        self.video_montage_list.setMinimumHeight(220)
        self.video_montage_list.setToolTip("Arrastra aquí varios vídeos o usa el botón Añadir vídeos.")
        video_montage_grid.addWidget(self.video_montage_list, 0, 1, 1, 6)

        self.video_montage_add_btn = QPushButton("Añadir vídeos")
        video_montage_grid.addWidget(self.video_montage_add_btn, 1, 1)
        self.video_montage_remove_btn = QPushButton("Quitar seleccionados")
        video_montage_grid.addWidget(self.video_montage_remove_btn, 1, 2)
        self.video_montage_clear_btn = QPushButton("Limpiar")
        video_montage_grid.addWidget(self.video_montage_clear_btn, 1, 3)

        video_montage_grid.addWidget(QLabel("Formato:"), 2, 0)
        self.video_montage_ratio_combo = QComboBox()
        self.video_montage_ratio_combo.addItem("Vertical 9:16", "9:16")
        self.video_montage_ratio_combo.addItem("Horizontal 16:9", "16:9")
        video_montage_grid.addWidget(self.video_montage_ratio_combo, 2, 1)

        video_montage_grid.addWidget(QLabel("Fundido entre vídeos:"), 2, 2)
        self.video_montage_transition_spin = QDoubleSpinBox()
        self.video_montage_transition_spin.setRange(0.0, 5.0)
        self.video_montage_transition_spin.setSingleStep(0.25)
        self.video_montage_transition_spin.setValue(0.75)
        video_montage_grid.addWidget(self.video_montage_transition_spin, 2, 3)

        self.video_montage_fade_out_checkbox = QCheckBox("Fundido final")
        self.video_montage_fade_out_checkbox.setChecked(True)
        video_montage_grid.addWidget(self.video_montage_fade_out_checkbox, 2, 4)

        self.video_montage_generate_btn = QPushButton("Crear montaje")
        video_montage_grid.addWidget(self.video_montage_generate_btn, 2, 5)
        video_montage_grid.setColumnStretch(6, 1)
        video_montage_layout.addWidget(video_montage_group)

        self.bulk_youtube_dialog = QDialog(self)
        self.bulk_youtube_dialog.setWindowTitle("Vídeo YouTube Bulk Images")
        self.bulk_youtube_dialog.setModal(False)
        bulk_youtube_layout = QVBoxLayout(self.bulk_youtube_dialog)
        bulk_youtube_group = QGroupBox("Crear vídeo YouTube 16:9 desde Bulk Images")
        bulk_youtube_grid = QGridLayout(bulk_youtube_group)
        bulk_youtube_grid.setHorizontalSpacing(10)
        bulk_youtube_grid.setVerticalSpacing(8)

        bulk_youtube_grid.addWidget(QLabel("Categoría Bulk:"), 0, 0)
        self.bulk_youtube_category_combo = QComboBox()
        self.bulk_youtube_category_combo.setMinimumWidth(280)
        bulk_youtube_grid.addWidget(self.bulk_youtube_category_combo, 0, 1, 1, 3)

        bulk_youtube_grid.addWidget(QLabel("Audio relax:"), 1, 0)
        self.bulk_youtube_audio_combo = QComboBox()
        self.bulk_youtube_audio_combo.setMinimumWidth(280)
        bulk_youtube_grid.addWidget(self.bulk_youtube_audio_combo, 1, 1, 1, 3)
        self.bulk_youtube_reload_audio_btn = QPushButton("Recargar audios")
        bulk_youtube_grid.addWidget(self.bulk_youtube_reload_audio_btn, 1, 4)

        bulk_youtube_grid.addWidget(QLabel("Segundos/imagen:"), 2, 0)
        self.bulk_youtube_seconds_spin = QDoubleSpinBox()
        self.bulk_youtube_seconds_spin.setRange(1.0, 60.0)
        self.bulk_youtube_seconds_spin.setSingleStep(0.5)
        self.bulk_youtube_seconds_spin.setValue(8.0)
        bulk_youtube_grid.addWidget(self.bulk_youtube_seconds_spin, 2, 1)

        bulk_youtube_grid.addWidget(QLabel("Fundido:"), 2, 2)
        self.bulk_youtube_transition_spin = QDoubleSpinBox()
        self.bulk_youtube_transition_spin.setRange(0.0, 5.0)
        self.bulk_youtube_transition_spin.setSingleStep(0.25)
        self.bulk_youtube_transition_spin.setValue(0.75)
        bulk_youtube_grid.addWidget(self.bulk_youtube_transition_spin, 2, 3)

        bulk_youtube_grid.addWidget(QLabel("Transición:"), 2, 4)
        self.bulk_youtube_transition_type_combo = QComboBox()
        for label, value in [
            ("Fundido", "fade"),
            ("Fundido negro", "fadeblack"),
            ("Fundido blanco", "fadewhite"),
            ("Disolver", "dissolve"),
            ("Pixelizar", "pixelize"),
            ("Barrido izquierda", "wipeleft"),
            ("Barrido derecha", "wiperight"),
            ("Barrido arriba", "wipeup"),
            ("Barrido abajo", "wipedown"),
            ("Deslizar izquierda", "slideleft"),
            ("Deslizar derecha", "slideright"),
            ("Círculo abre", "circleopen"),
            ("Círculo cierra", "circleclose"),
        ]:
            self.bulk_youtube_transition_type_combo.addItem(label, value)
        bulk_youtube_grid.addWidget(self.bulk_youtube_transition_type_combo, 2, 5)

        bulk_youtube_grid.addWidget(QLabel("Resolución:"), 3, 0)
        self.bulk_youtube_resolution_combo = QComboBox()
        self.bulk_youtube_resolution_combo.addItem("4K (3840x2160)", "4k")
        self.bulk_youtube_resolution_combo.addItem("1080p (1920x1080)", "1080p")
        bulk_youtube_grid.addWidget(self.bulk_youtube_resolution_combo, 3, 1)

        self.bulk_youtube_generate_btn = QPushButton("Crear vídeo YouTube")
        bulk_youtube_grid.addWidget(self.bulk_youtube_generate_btn, 3, 3, 1, 2)

        self.bulk_youtube_plan_label = QLabel("Selecciona categoría y audio para calcular imágenes necesarias.")
        self.bulk_youtube_plan_label.setWordWrap(True)
        bulk_youtube_grid.addWidget(self.bulk_youtube_plan_label, 4, 0, 1, 6)
        bulk_youtube_grid.setColumnStretch(6, 1)
        bulk_youtube_layout.addWidget(bulk_youtube_group)
        self._populate_bulk_youtube_category_combo()
        self._populate_bulk_youtube_audio_combo()
        self._update_bulk_youtube_plan_label()

        self.dollimages_reel_dialog = QDialog(self)
        self.dollimages_reel_dialog.setWindowTitle("Reel Dollimages")
        self.dollimages_reel_dialog.setModal(False)
        doll_reel_layout = QVBoxLayout(self.dollimages_reel_dialog)
        doll_reel_group = QGroupBox("Reel Dollimages")
        doll_reel_grid = QGridLayout(doll_reel_group)
        doll_reel_grid.setHorizontalSpacing(10)
        doll_reel_grid.setVerticalSpacing(8)

        doll_reel_grid.addWidget(QLabel("Grupo:"), 0, 0)
        self.dollimages_reel_group_combo = QComboBox()
        self.dollimages_reel_group_combo.setMinimumWidth(160)
        doll_reel_grid.addWidget(self.dollimages_reel_group_combo, 0, 1)

        doll_reel_grid.addWidget(QLabel("Tipología:"), 0, 2)
        self.dollimages_reel_typology_combo = QComboBox()
        self.dollimages_reel_typology_combo.addItem("Todas", None)
        self.dollimages_reel_typology_combo.addItem("Normal", "normal")
        self.dollimages_reel_typology_combo.addItem("SFW", "sfw")
        self.dollimages_reel_typology_combo.addItem("NSFW", "nsfw")
        doll_reel_grid.addWidget(self.dollimages_reel_typology_combo, 0, 3)

        doll_reel_grid.addWidget(QLabel("Cantidad imágenes:"), 0, 4)
        self.dollimages_reel_quantity_spin = QSpinBox()
        self.dollimages_reel_quantity_spin.setRange(1, 30)
        self.dollimages_reel_quantity_spin.setValue(5)
        doll_reel_grid.addWidget(self.dollimages_reel_quantity_spin, 0, 5)
        doll_reel_grid.addWidget(QLabel("Disponibles:"), 1, 4)
        self.dollimages_reel_available_label = QLabel("—")
        doll_reel_grid.addWidget(self.dollimages_reel_available_label, 1, 5)

        doll_reel_grid.addWidget(QLabel("Segundos por imagen:"), 0, 6)
        self.dollimages_reel_seconds_spin = QDoubleSpinBox()
        self.dollimages_reel_seconds_spin.setRange(1.0, 10.0)
        self.dollimages_reel_seconds_spin.setSingleStep(0.5)
        self.dollimages_reel_seconds_spin.setValue(2.0)
        doll_reel_grid.addWidget(self.dollimages_reel_seconds_spin, 0, 7)

        doll_reel_grid.addWidget(QLabel("Redes (manual):"), 1, 0)
        self.dollimages_reel_social_input = QLineEdit()
        self.dollimages_reel_social_input.setPlaceholderText("Ej: @dollimages / @instagram")
        doll_reel_grid.addWidget(self.dollimages_reel_social_input, 1, 1, 1, 3)
        doll_reel_grid.addWidget(QLabel("Fundido final:"), 1, 6)
        self.dollimages_reel_fade_out_checkbox = QCheckBox()
        self.dollimages_reel_fade_out_checkbox.setChecked(True)
        doll_reel_grid.addWidget(self.dollimages_reel_fade_out_checkbox, 1, 7)

        doll_reel_grid.addWidget(QLabel("Mostrar título:"), 2, 0)
        self.dollimages_reel_overlay_title_checkbox = QCheckBox()
        self.dollimages_reel_overlay_title_checkbox.setChecked(True)
        doll_reel_grid.addWidget(self.dollimages_reel_overlay_title_checkbox, 2, 1)

        self.dollimages_reel_generate_btn = QPushButton("Crear Reel")
        doll_reel_grid.addWidget(self.dollimages_reel_generate_btn, 0, 8)
        doll_reel_grid.setColumnStretch(9, 1)

        doll_reel_layout.addWidget(doll_reel_group)


        self.anime_v5_reel_dialog = QDialog(self)
        self.anime_v5_reel_dialog.setWindowTitle("Reel Anime V5")
        self.anime_v5_reel_dialog.setModal(False)
        anime_reel_layout = QVBoxLayout(self.anime_v5_reel_dialog)
        anime_reel_group = QGroupBox("Reel Anime V5 sin textos")
        anime_reel_grid = QGridLayout(anime_reel_group)
        anime_reel_grid.setHorizontalSpacing(10)
        anime_reel_grid.setVerticalSpacing(8)
        anime_reel_grid.addWidget(QLabel("Lista:"), 0, 0)
        self.anime_v5_reel_list_combo = QComboBox()
        self.anime_v5_reel_list_combo.addItem("Todas", None)
        anime_reel_grid.addWidget(self.anime_v5_reel_list_combo, 0, 1)
        anime_reel_grid.addWidget(QLabel("Personaje:"), 0, 2)
        self.anime_v5_reel_character_combo = QComboBox()
        self.anime_v5_reel_character_combo.addItem("Aleatorio / todos", None)
        anime_reel_grid.addWidget(self.anime_v5_reel_character_combo, 0, 3)
        anime_reel_grid.addWidget(QLabel("Cantidad (0 = aleatoria):"), 0, 4)
        self.anime_v5_reel_quantity_spin = QSpinBox()
        self.anime_v5_reel_quantity_spin.setRange(0, 100)
        self.anime_v5_reel_quantity_spin.setValue(0)
        anime_reel_grid.addWidget(self.anime_v5_reel_quantity_spin, 0, 5)
        anime_reel_grid.addWidget(QLabel("Segundos imagen:"), 1, 0)
        self.anime_v5_reel_seconds_spin = QDoubleSpinBox()
        self.anime_v5_reel_seconds_spin.setRange(1.0, 10.0)
        self.anime_v5_reel_seconds_spin.setSingleStep(0.5)
        self.anime_v5_reel_seconds_spin.setValue(2.0)
        anime_reel_grid.addWidget(self.anime_v5_reel_seconds_spin, 1, 1)
        anime_reel_grid.addWidget(QLabel("Transición:"), 1, 2)
        self.anime_v5_reel_transition_spin = QDoubleSpinBox()
        self.anime_v5_reel_transition_spin.setRange(0.1, 5.0)
        self.anime_v5_reel_transition_spin.setSingleStep(0.1)
        self.anime_v5_reel_transition_spin.setValue(0.5)
        anime_reel_grid.addWidget(self.anime_v5_reel_transition_spin, 1, 3)
        anime_reel_grid.addWidget(QLabel("Fundido final:"), 1, 4)
        self.anime_v5_reel_fade_out_checkbox = QCheckBox()
        self.anime_v5_reel_fade_out_checkbox.setChecked(True)
        anime_reel_grid.addWidget(self.anime_v5_reel_fade_out_checkbox, 1, 5)
        anime_reel_grid.addWidget(QLabel("Incluir NSFW:"), 2, 0)
        self.anime_v5_reel_include_nsfw_checkbox = QCheckBox()
        self.anime_v5_reel_include_nsfw_checkbox.setChecked(False)
        self.anime_v5_reel_include_nsfw_checkbox.setToolTip("Desactiva esta opción para crear el reel solo con imágenes Anime V5 SFW.")
        anime_reel_grid.addWidget(self.anime_v5_reel_include_nsfw_checkbox, 2, 1)
        self.anime_v5_reel_generate_btn = QPushButton("Crear Reel Anime V5")
        anime_reel_grid.addWidget(self.anime_v5_reel_generate_btn, 2, 4, 1, 2)
        anime_reel_grid.setColumnStretch(6, 1)
        anime_reel_layout.addWidget(anime_reel_group)

        main_content = QHBoxLayout()
        layout.addLayout(main_content, 1)
        self.main_content_layout = main_content

        left_column_widget = QWidget()
        left_column = QVBoxLayout(left_column_widget)
        main_content.addWidget(left_column_widget, 7)
        self.left_column_widget = left_column_widget

        right_column_widget = QWidget()
        right_column = QVBoxLayout(right_column_widget)
        main_content.addWidget(right_column_widget, 3)
        self.right_column_widget = right_column_widget

        # Table
        self.table = QTableWidget(0, 14)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Categoría",
            "Base",
            "Upscale",
            "Reel",
            "Prioridad Reel",
            "Descartada Reel",
            "Versión",
            "Estado",
            "Fecha",
            "Título",
            "Ratio",
            "Checkpoint Base",
            "Checkpoint Refiner",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)

        # 1) Quita las marcas de foco en Windows 11
        self.table.setStyle(NoFocusRectStyle(self.table.style()))

        # 2) Fuerza colores de selección (fondo + texto) a nivel de palette
        pal = self.table.palette()
        pal.setColor(QPalette.Highlight, QColor("#2b2f36"))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.table.setPalette(pal)

        # 3) Refuerza en QSS (incluye estados active/inactive para que SIEMPRE se vea el texto)
        self._style_table_selection()

        left_column.addWidget(self.table, 1)

        # Base preview group (right column)
        self.base_group = QGroupBox("Preview Base")
        base_layout = QVBoxLayout(self.base_group)
        self.base_preview_stack = QStackedWidget()
        base_layout.addWidget(self.base_preview_stack)

        self.base_image_label = ClickableLabel("(sin base)")
        self.base_image_label.setAlignment(Qt.AlignCenter)
        self.base_image_label.setMinimumHeight(240)
        self.base_image_label.setObjectName("PreviewSurface")
        self.base_preview_stack.addWidget(self.base_image_label)

        self.base_video_widget = QVideoWidget()
        self.base_video_widget.setMinimumHeight(240)
        self.base_video_widget.setObjectName("PreviewSurface")
        self.base_preview_stack.addWidget(self.base_video_widget)

        self.base_video_player = QMediaPlayer(self)
        self.base_video_audio = QAudioOutput(self)
        # Keep preview audio enabled so Cloudinary videos with music can be validated in-app.
        self.base_video_audio.setVolume(1.0)
        self.base_video_player.setAudioOutput(self.base_video_audio)
        self.base_video_player.setVideoOutput(self.base_video_widget)
        self.base_video_player.mediaStatusChanged.connect(self._on_base_video_status_changed)

        base_video_controls = QHBoxLayout()
        self.base_video_play_btn = QPushButton("Play")
        self.base_video_stop_btn = QPushButton("Stop")
        self.base_video_play_btn.setEnabled(False)
        self.base_video_stop_btn.setEnabled(False)
        base_video_controls.addStretch(1)
        base_video_controls.addWidget(self.base_video_play_btn)
        base_video_controls.addWidget(self.base_video_stop_btn)
        base_layout.addLayout(base_video_controls)

        self.base_image_label.doubleClicked.connect(lambda: self.open_preview_dialog("base"))

        self.base_group.setVisible(False)
        right_column.addWidget(self.base_group, 3)

        # Worker log group (right column)
        self.worker_log_group = QGroupBox("Log del Worker")
        worker_log_layout = QVBoxLayout(self.worker_log_group)
        self.worker_log_text = QPlainTextEdit("—")
        self.worker_log_text.setReadOnly(True)
        self.worker_log_text.document().setMaximumBlockCount(300)
        worker_log_layout.addWidget(self.worker_log_text)

        worker_log_actions = QHBoxLayout()
        self.clear_worker_log_btn = QPushButton("Limpiar log")
        worker_log_actions.addStretch(1)
        worker_log_actions.addWidget(self.clear_worker_log_btn)
        worker_log_layout.addLayout(worker_log_actions)

        right_column.addWidget(self.worker_log_group, 2)

        self.production_dialog = QDialog(self)
        self.production_dialog.setWindowTitle("Producción por categoría")
        self.production_dialog.setModal(False)
        production_dialog_layout = QVBoxLayout(self.production_dialog)
        production_row = QHBoxLayout()
        production_row.addWidget(QLabel("Producción por categoría:"))
        production_dialog_layout.addLayout(production_row)

        self.category_production_table = QTableWidget(0, 2)
        self.category_production_table.setHorizontalHeaderLabels(["Categoría", "Total"])
        self.category_production_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.category_production_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.category_production_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.category_production_table.verticalHeader().setVisible(False)
        self.category_production_table.horizontalHeader().setStretchLastSection(True)
        self.category_production_table.setMinimumHeight(240)
        production_dialog_layout.addWidget(self.category_production_table)
        production_close_btn = QPushButton("Cerrar")
        production_close_btn.clicked.connect(self.production_dialog.close)
        production_dialog_layout.addWidget(production_close_btn, alignment=Qt.AlignRight)

        # Signals
        self.refresh_action.triggered.connect(self.refresh)
        self.pause_action.triggered.connect(self.pause_queue)
        self.resume_action.triggered.connect(self.resume_queue)
        self.clear_queued_action.triggered.connect(self.clear_queued_prompts)
        self.mark_reel_priority_action.triggered.connect(self.mark_selected_reel_priority)
        self.mark_reel_discard_action.triggered.connect(self.mark_selected_reel_discarded)
        self.clear_reel_flags_action.triggered.connect(self.clear_selected_reel_flags)

        self.open_base_action.triggered.connect(lambda: self.open_selected("base"))
        self.open_up_action.triggered.connect(lambda: self.open_selected("upscale"))
        self.open_folder_base_action.triggered.connect(lambda: self.open_selected("folder_base"))
        self.open_folder_up_action.triggered.connect(lambda: self.open_selected("folder_upscale"))
        self.open_video_action.triggered.connect(lambda: self.open_selected("video"))
        self.open_folder_video_action.triggered.connect(lambda: self.open_selected("folder_video"))
        # Selection changes => enable/disable + preview update
        self.table.itemSelectionChanged.connect(self._sync_current_cell_to_selection)
        self.table.itemSelectionChanged.connect(self.update_actions_state)
        self.table.itemDoubleClicked.connect(self.open_prompt_dialog_from_item)

        # Estado inicial botones (deshabilitados hasta tener selección válida)
        self.open_base_action.setEnabled(False)
        self.open_up_action.setEnabled(False)
        self.open_folder_base_action.setEnabled(False)
        self.open_folder_up_action.setEnabled(False)
        self.open_video_action.setEnabled(False)
        self.open_folder_video_action.setEnabled(False)
        self.mark_reel_priority_action.setEnabled(False)
        self.mark_reel_discard_action.setEnabled(False)
        self.clear_reel_flags_action.setEnabled(False)
        self.worker_thread: WorkerThread | None = None

        self.start_worker_btn.clicked.connect(self.start_worker)
        self.stop_worker_btn.clicked.connect(self.stop_worker)
        self.clear_queued_btn.clicked.connect(self.clear_queued_prompts)
        self.pack_generate_btn.clicked.connect(self.generate_pack)
        self.manual_prompt_generate_btn.clicked.connect(self.generate_manual_prompt)
        self.dollimages_generate_btn.clicked.connect(self.generate_dollimages_pack)
        self.dollimages_manual_generate_btn.clicked.connect(self.generate_dollimages_manual_prompt)
        self.reel_generate_btn.clicked.connect(self.generate_reel)
        self.video_montage_generate_btn.clicked.connect(self.generate_video_montage)
        self.bulk_youtube_generate_btn.clicked.connect(self.generate_bulk_youtube_video)
        self.bulk_youtube_reload_audio_btn.clicked.connect(self._populate_bulk_youtube_audio_combo)
        self.bulk_youtube_category_combo.currentIndexChanged.connect(self._update_bulk_youtube_plan_label)
        self.bulk_youtube_audio_combo.currentIndexChanged.connect(self._update_bulk_youtube_plan_label)
        self.bulk_youtube_seconds_spin.valueChanged.connect(self._update_bulk_youtube_plan_label)
        self.bulk_youtube_transition_spin.valueChanged.connect(self._update_bulk_youtube_plan_label)
        self.bulk_youtube_transition_type_combo.currentIndexChanged.connect(self._update_bulk_youtube_plan_label)
        self.video_montage_add_btn.clicked.connect(self.add_video_montage_files)
        self.video_montage_remove_btn.clicked.connect(self.remove_selected_video_montage_files)
        self.video_montage_clear_btn.clicked.connect(self.video_montage_list.clear)
        self.dollimages_reel_generate_btn.clicked.connect(self.generate_dollimages_reel)
        self.image2vid_generate_btn.clicked.connect(self.generate_image2vid)
        self.undress_generate_btn.clicked.connect(self.generate_undress)
        self.open_filters_btn.clicked.connect(self.filters_dialog.show)
        self.open_pack_btn.clicked.connect(self.pack_dialog.show)
        self.open_manual_prompt_btn.clicked.connect(self.manual_prompt_dialog.show)
        self.open_dollimages_pack_btn.clicked.connect(self.dollimages_dialog.show)
        self.open_dollimages_manual_prompt_btn.clicked.connect(self.dollimages_manual_dialog.show)
        self.open_image2vid_btn.clicked.connect(self.open_image2vid_dialog)
        self.open_undress_btn.clicked.connect(self.open_undress_dialog)
        self.open_anime_v5_btn.clicked.connect(self.anime_v5_dialog.show)
        self.open_bulk_images_btn.clicked.connect(self.open_bulk_images_prompt_window)
        self.anime_v5_generate_btn.clicked.connect(self.generate_anime_v5)
        self.anime_v5_maintenance_btn.clicked.connect(self.open_anime_v5_maintenance_window)
        self.anime_v5_select_all_lists_btn.clicked.connect(self._select_all_anime_v5_lists)
        self.anime_v5_clear_lists_btn.clicked.connect(self.anime_v5_list_selection.clearSelection)
        self.anime_v5_list_selection.itemSelectionChanged.connect(self._populate_anime_v5_single_character_options)
        self.anime_v5_list_combo.currentIndexChanged.connect(self._load_anime_v5_list_from_combo)
        self.anime_v5_list_combo.currentTextChanged.connect(lambda _text: self._populate_anime_v5_single_character_options())
        self.anime_v5_characters_input.textChanged.connect(self._populate_anime_v5_single_character_options)
        self.anime_v5_pick_prompt_btn.clicked.connect(self.open_anime_v5_prompt_picker)
        self.anime_v5_generator_btn.clicked.connect(self.apply_anime_v5_generator_template)
        self.anime_v5_prompt_cancel_btn.clicked.connect(self.anime_v5_prompt_picker_dialog.reject)
        self.anime_v5_prompt_apply_btn.clicked.connect(self._apply_selected_anime_v5_prompt)
        self.anime_v5_prompt_search_input.textChanged.connect(self._filter_anime_v5_prompts)
        self.anime_v5_prompt_table.itemDoubleClicked.connect(lambda _item: self._apply_selected_anime_v5_prompt())
        self.open_reel_btn.clicked.connect(self.reel_dialog.show)
        self.open_video_montage_btn.clicked.connect(self.video_montage_dialog.show)
        self.open_bulk_youtube_btn.clicked.connect(self.open_bulk_youtube_dialog)
        self.open_dollimages_reel_btn.clicked.connect(self.dollimages_reel_dialog.show)
        self.open_anime_v5_reel_btn.clicked.connect(self.anime_v5_reel_dialog.show)
        self.anime_v5_reel_generate_btn.clicked.connect(self.generate_anime_v5_reel)
        self.anime_v5_reel_list_combo.currentIndexChanged.connect(self._populate_anime_v5_reel_characters)
        self.dollimages_reference_btn.clicked.connect(self.select_dollimages_reference_image)
        self.dollimages_manual_reference_btn.clicked.connect(
            self.select_dollimages_manual_reference_image
        )
        self.dollimages_faceswap_check.toggled.connect(self._toggle_dollimages_faceswap_inputs)
        self.dollimages_manual_faceswap_check.toggled.connect(
            self._toggle_dollimages_manual_faceswap_inputs
        )
        self.dollimages_workflow_combo.currentIndexChanged.connect(
            self._update_dollimages_workflow_controls
        )
        self.dollimages_manual_workflow_combo.currentIndexChanged.connect(
            self._update_dollimages_manual_workflow_controls
        )
        self.limit_spin.valueChanged.connect(self.refresh)
        self.pause_between_spin.valueChanged.connect(self._update_worker_delay)
        self.prompt_id_input.textChanged.connect(self.refresh)
        self.filter_category_combo.currentIndexChanged.connect(self.refresh)
        self.filter_variant_combo.currentIndexChanged.connect(self.refresh)
        self.filter_status_combo.currentIndexChanged.connect(self.refresh)
        self.filter_ratio_combo.currentIndexChanged.connect(self.refresh)
        self.filter_checkpoint_base_combo.currentIndexChanged.connect(self.refresh)
        self.filter_from_datetime.dateTimeChanged.connect(self.refresh)
        self.filter_to_datetime.dateTimeChanged.connect(self.refresh)
        self.filter_date_order_combo.currentIndexChanged.connect(self.refresh)
        self.filter_last_days_spin.valueChanged.connect(self._on_last_days_changed)
        self.reel_category_combo.currentIndexChanged.connect(self._populate_reel_variants)
        self.image2vid_ratio_combo.currentIndexChanged.connect(self._update_image2vid_labels)
        self.image2vid_seconds_spin.valueChanged.connect(self._update_image2vid_labels)
        self.undress_select_source_btn.clicked.connect(self._set_undress_source_from_current_selection)
        self.undress_garment_list.itemChanged.connect(self._update_undress_prompt)
        self.image2vid_reload_sources_btn.clicked.connect(self._set_image2vid_source_from_current_selection)
        self.image2vid_select_source_btn.clicked.connect(self._set_image2vid_source_from_current_selection)
        self.image2vid_pick_prompt_btn.clicked.connect(self.open_image2vid_prompt_picker)
        self.image2vid_source_cancel_btn.clicked.connect(self.image2vid_source_picker_dialog.reject)
        self.image2vid_prompt_cancel_btn.clicked.connect(self.image2vid_prompt_picker_dialog.reject)
        self.image2vid_prompt_apply_btn.clicked.connect(self._apply_selected_image2vid_prompt_template)
        self.image2vid_prompt_search_input.textChanged.connect(self._filter_image2vid_prompt_templates)
        self.image2vid_prompt_table.itemDoubleClicked.connect(
            lambda _item: self._apply_selected_image2vid_prompt_template()
        )
        self.image2vid_source_apply_btn.clicked.connect(self._apply_selected_image2vid_source)
        self.image2vid_source_table.itemSelectionChanged.connect(self._update_image2vid_source_preview)
        self.image2vid_source_table.itemDoubleClicked.connect(
            lambda _item: self._apply_selected_image2vid_source()
        )
        self.image2vid_filter_category_combo.currentIndexChanged.connect(
            self._apply_image2vid_source_filters
        )
        self.image2vid_filter_variant_combo.currentIndexChanged.connect(
            self._apply_image2vid_source_filters
        )
        self.manual_prompt_category_combo.currentIndexChanged.connect(self._update_manual_prompt_ratios)
        self.manual_prompt_checkpoint_combo.currentIndexChanged.connect(
            self._sync_manual_prompt_refiner_label
        )
        self.dollimages_reel_group_combo.currentIndexChanged.connect(
            self._update_dollimages_reel_availability
        )
        self.dollimages_reel_typology_combo.currentIndexChanged.connect(
            self._update_dollimages_reel_availability
        )
        self.reset_filters_btn.clicked.connect(self.reset_filters)
        self.toggle_preview_action.toggled.connect(self._toggle_base_preview)
        self.preview_toggle_check.toggled.connect(self._toggle_base_preview)
        self.preview_auto_disable_spin.valueChanged.connect(self._restart_preview_auto_disable_timer)
        self.toggle_worker_log_action.toggled.connect(self._toggle_worker_log)
        self.clear_worker_log_btn.clicked.connect(self.clear_worker_log)
        self.base_video_play_btn.clicked.connect(self._play_base_video_preview)
        self.base_video_stop_btn.clicked.connect(self._stop_base_video_preview)
        self.pack_combination_combo.currentIndexChanged.connect(self._update_nsfw_controls)
        self._populate_pack_selectors()
        self._populate_checkpoint_selectors()
        self._populate_manual_prompt_selectors()
        self._populate_dollimages_groups()
        self._update_image2vid_labels()
        self._update_dollimages_reel_availability()
        self._update_nsfw_controls()
        self._update_dollimages_workflow_controls()
        self._update_dollimages_manual_workflow_controls()
        self._populate_anime_v5_lists()
        self._populate_anime_v5_reel_selectors()
        self._load_anime_v5_prompts()
        self._populate_anime_v5_fixed_outfits()
        self._load_image2vid_prompt_templates()

        self._update_right_column_visibility()
        self._relayout_responsive_panels()
        self.prompt_dialog: PromptDetailDialog | None = None
        self.refresh()

    def _sync_current_cell_to_selection(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        r = selected[0].row()
        # deja como "current cell" la columna 0 (ID), así no pinta focus raro en columnas vacías
        self.table.setCurrentCell(r, 0)

    def _clear_current_cell(self) -> None:
        # Evita que Qt dibuje el indicador de "celda actual" (rayas azules)
        self.table.setCurrentCell(-1, -1)

    def _toggle_dollimages_faceswap_inputs(self, enabled: bool) -> None:
        self.dollimages_reference_input.setEnabled(enabled)
        self.dollimages_reference_btn.setEnabled(enabled)

    def _toggle_dollimages_manual_faceswap_inputs(self, enabled: bool) -> None:
        self.dollimages_manual_reference_input.setEnabled(enabled)
        self.dollimages_manual_reference_btn.setEnabled(enabled)

    def _update_dollimages_workflow_controls(self) -> None:
        workflow_key = self.dollimages_workflow_combo.currentData()
        faceswap_allowed = workflow_key == "dollimages"
        checkpoint_allowed = workflow_key == "dollimages"

        self.dollimages_faceswap_check.setEnabled(faceswap_allowed)
        if not faceswap_allowed:
            self.dollimages_faceswap_check.setChecked(False)
        self._toggle_dollimages_faceswap_inputs(
            faceswap_allowed and self.dollimages_faceswap_check.isChecked()
        )
        self.dollimages_checkpoint_combo.setEnabled(checkpoint_allowed)

    def _update_dollimages_manual_workflow_controls(self) -> None:
        workflow_key = self.dollimages_manual_workflow_combo.currentData()
        faceswap_allowed = workflow_key == "dollimages"
        checkpoint_allowed = workflow_key == "dollimages"

        self.dollimages_manual_faceswap_check.setEnabled(faceswap_allowed)
        if not faceswap_allowed:
            self.dollimages_manual_faceswap_check.setChecked(False)
        self._toggle_dollimages_manual_faceswap_inputs(
            faceswap_allowed and self.dollimages_manual_faceswap_check.isChecked()
        )
        self.dollimages_manual_checkpoint_combo.setEnabled(checkpoint_allowed)

    # -------- Queue controls --------

    def pause_queue(self) -> None:
        self.store.kv_set("queue_paused", "true")

        self.refresh()
        QMessageBox.information(self, "Cola", "Cola pausada.")

    def resume_queue(self) -> None:
        self.store.kv_set("queue_paused", "false")
        if self.worker_thread:
            self.worker_thread.worker.recover_inflight_jobs()
        self.refresh()
        QMessageBox.information(self, "Cola", "Cola reanudada.")

    def clear_queued_prompts(self) -> None:
        queued_count = 0
        if self._cached_status_counts is not None:
            queued_count = self._cached_status_counts.get("QUEUED", 0)

        confirm = QMessageBox.question(
            self,
            "Borrar QUEUED",
            (
                "¿Borrar de la cola todos los prompts en estado QUEUED?\n"
                f"Prompts QUEUED detectados: {queued_count}"
            ),
        )
        if confirm != QMessageBox.Yes:
            return

        deleted_count = self.store.delete_queued_prompt_items()
        self.refresh()
        QMessageBox.information(
            self,
            "Borrar QUEUED",
            f"Prompts QUEUED eliminados: {deleted_count}.",
        )

    # -------- Table / Data --------

    def _schedule_refresh(self, *, resize_columns: bool = False) -> None:
        if resize_columns:
            self._refresh_resize_columns = True
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(300)

    def _run_scheduled_refresh(self) -> None:
        resize_columns = self._refresh_resize_columns
        self._refresh_resize_columns = False
        self._start_refresh(resize_columns=resize_columns)

    def refresh(self) -> None:
        self._schedule_refresh(resize_columns=True)

    def _collect_refresh_params(self) -> dict[str, object]:
        return {
            "limit": int(self.limit_spin.value()),
            "prompt_id": self._selected_prompt_id_filter(),
            "category": self._selected_filter_value(self.filter_category_combo),
            "variant": self._selected_filter_value(self.filter_variant_combo),
            "status": self._selected_filter_value(self.filter_status_combo),
            "ratio": self._selected_filter_value(self.filter_ratio_combo),
            "checkpoint_base": self._selected_filter_value(self.filter_checkpoint_base_combo),
            "date_from": self._selected_datetime_value(self.filter_from_datetime),
            "date_to": self._selected_datetime_value(self.filter_to_datetime),
            "sort_order": self._selected_sort_order(),
        }

    def _start_refresh(self, *, resize_columns: bool) -> None:
        if self._refresh_worker and self._refresh_worker.isRunning():
            self._refresh_pending = True
            if resize_columns:
                self._refresh_resize_columns = True
            return

        params = self._collect_refresh_params()
        worker = RefreshWorker(
            limit=int(params["limit"]),
            prompt_id=params["prompt_id"],
            category=params["category"],
            variant=params["variant"],
            status=params["status"],
            ratio=params["ratio"],
            checkpoint_base=params["checkpoint_base"],
            date_from=params["date_from"],
            date_to=params["date_to"],
            sort_order=str(params["sort_order"]),
            resize_columns=resize_columns,
            parent=self,
        )
        worker.result.connect(self._on_refresh_result)
        worker.failed.connect(self._on_refresh_failed)
        worker.finished.connect(lambda worker=worker: self._clear_refresh_worker(worker))
        worker.finished.connect(worker.deleteLater)
        self._refresh_worker = worker
        worker.start()

    def _clear_refresh_worker(self, worker: RefreshWorker) -> None:
        if self._refresh_worker is not worker:
            return
        self._refresh_worker = None
        if self._refresh_pending:
            self._refresh_pending = False
            resize_columns = self._refresh_resize_columns
            self._refresh_resize_columns = False
            self._start_refresh(resize_columns=resize_columns)

    def _on_refresh_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Error de refresco", message)

    def _on_refresh_result(self, payload: RefreshPayload) -> None:
        self._apply_refresh_result(payload)

    def _apply_refresh_result(self, payload: RefreshPayload) -> None:
        data = payload.rows
        previous_updates_enabled = self.table.updatesEnabled()
        previous_sorting_enabled = self.table.isSortingEnabled()
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(data))
            for i, row in enumerate(data):
                id_item = QTableWidgetItem(str(row.id))
                id_item.setData(Qt.UserRole, row.progress)
                id_item.setData(Qt.UserRole + 1, row.backend_status)
                self.table.setItem(i, 0, id_item)
                self.table.setItem(i, 1, QTableWidgetItem(row.category))
                self.table.setItem(i, 2, QTableWidgetItem("✅" if row.has_base else "—"))
                self.table.setItem(i, 3, QTableWidgetItem("✅" if row.has_upscale else "—"))
                self.table.setItem(i, 4, QTableWidgetItem("✅" if row.used_in_reel else "—"))
                self.table.setItem(i, 5, QTableWidgetItem("⭐" if row.reel_priority else "—"))
                self.table.setItem(i, 6, QTableWidgetItem("⛔" if row.reel_discarded else "—"))
                self.table.setItem(i, 7, QTableWidgetItem(row.variant))
                self.table.setItem(i, 8, QTableWidgetItem(row.status))
                self.table.setItem(i, 9, QTableWidgetItem(row.datestamp))
                self.table.setItem(i, 10, QTableWidgetItem(row.title))
                self.table.setItem(i, 11, QTableWidgetItem(row.ratio))
                self.table.setItem(i, 12, QTableWidgetItem(row.checkpoint_base or "—"))
                self.table.setItem(i, 13, QTableWidgetItem(row.checkpoint_refiner or "—"))

            if payload.resize_columns:
                self.table.resizeColumnsToContents()
        finally:
            self.table.blockSignals(False)
            self.table.setSortingEnabled(previous_sorting_enabled)
            self.table.setUpdatesEnabled(previous_updates_enabled)

        # Recalcular botones + preview tras refrescar
        self.update_actions_state()

        if payload.filters:
            self._cached_filters = payload.filters
            self._refresh_filters(filters=payload.filters)
        self._cached_status_counts = payload.status_counts
        self._refresh_status_counts(counts=payload.status_counts)
        if payload.category_counts:
            self._cached_category_counts = payload.category_counts
            self._refresh_category_production_counts(counts=payload.category_counts)

        is_paused = payload.is_paused
        self.pause_action.setEnabled(not is_paused)
        self.resume_action.setEnabled(is_paused)

    def _selected_prompt_id(self) -> int | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        pid_item = self.table.item(row, 0)
        if not pid_item:
            return None
        return int(pid_item.text())

    def _selected_prompt_backend_status(self) -> str | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        pid_item = self.table.item(row, 0)
        if not pid_item:
            return None
        value = pid_item.data(Qt.UserRole + 1)
        if isinstance(value, str) and value.strip():
            return value
        return None

    def _prompt_id_for_row(self, row: int) -> int | None:
        pid_item = self.table.item(row, 0)
        if not pid_item:
            return None
        return int(pid_item.text())

    def _backend_status_for_row(self, row: int) -> str | None:
        pid_item = self.table.item(row, 0)
        if not pid_item:
            return None
        value = pid_item.data(Qt.UserRole + 1)
        if isinstance(value, str) and value.strip():
            return value
        return None

    def _reload_waifu_catalog(self) -> None:
        self.waifu_catalog = load_waifu_catalog()

    def open_production_dialog(self) -> None:
        self._refresh_category_production_counts()
        self.production_dialog.show()
        self.production_dialog.raise_()
        self.production_dialog.activateWindow()

    def open_prompt_base_window(self) -> None:
        if self.prompt_base_window and self.prompt_base_window.isVisible():
            self.prompt_base_window.activateWindow()
            self.prompt_base_window.raise_()
            return
        window = PromptBaseWindow()
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.catalog_updated.connect(self.on_prompt_base_updated)
        window.destroyed.connect(self._clear_prompt_base_window)
        self.prompt_base_window = window
        window.show()

    def _clear_prompt_base_window(self) -> None:
        self.prompt_base_window = None

    def open_prompt_variation_window(self) -> None:
        if self.prompt_variation_window and self.prompt_variation_window.isVisible():
            self.prompt_variation_window.activateWindow()
            self.prompt_variation_window.raise_()
            return
        window = PromptVariationWindow()
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.catalog_updated.connect(self.on_prompt_base_updated)
        window.destroyed.connect(self._clear_prompt_variation_window)
        self.prompt_variation_window = window
        window.show()

    def _clear_prompt_variation_window(self) -> None:
        self.prompt_variation_window = None

    def open_social_copy_window(self) -> None:
        if self.social_copy_window and self.social_copy_window.isVisible():
            self.social_copy_window.activateWindow()
            self.social_copy_window.raise_()
            return
        window = SocialCopyWindow()
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.destroyed.connect(self._clear_social_copy_window)
        self.social_copy_window = window
        window.show()

    def _clear_social_copy_window(self) -> None:
        self.social_copy_window = None

    def open_dollimages_prompt_window(self) -> None:
        if self.dollimages_prompt_window and self.dollimages_prompt_window.isVisible():
            self.dollimages_prompt_window.activateWindow()
            self.dollimages_prompt_window.raise_()
            return
        window = DollimagesPromptWindow()
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.catalog_updated.connect(self._populate_dollimages_groups)
        window.generate_selected_requested.connect(self.prepare_selected_dollimages_prompt)
        window.destroyed.connect(self._clear_dollimages_prompt_window)
        self.dollimages_prompt_window = window
        window.show()

    def _clear_dollimages_prompt_window(self) -> None:
        self.dollimages_prompt_window = None

    def prepare_selected_dollimages_prompt(self, prompt_row: Any) -> None:
        typology_index = self.dollimages_manual_typology_combo.findData(prompt_row.typology)
        if typology_index >= 0:
            self.dollimages_manual_typology_combo.setCurrentIndex(typology_index)
        self.dollimages_manual_title_input.setText(prompt_row.title)
        self.dollimages_manual_prompt_text_input.setPlainText(prompt_row.prompt_text)
        self.dollimages_manual_dialog.show()
        self.dollimages_manual_dialog.activateWindow()
        self.dollimages_manual_dialog.raise_()
        self.dollimages_manual_generate_btn.setFocus(Qt.OtherFocusReason)

    def open_video_prompt_template_window(self) -> None:
        if self.video_prompt_template_window and self.video_prompt_template_window.isVisible():
            self.video_prompt_template_window.activateWindow()
            self.video_prompt_template_window.raise_()
            return
        window = VideoPromptTemplateWindow()
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.catalog_updated.connect(self._load_image2vid_prompt_templates)
        window.destroyed.connect(self._clear_video_prompt_template_window)
        self.video_prompt_template_window = window
        window.show()

    def _clear_video_prompt_template_window(self) -> None:
        self.video_prompt_template_window = None


    def open_bulk_images_prompt_window(self) -> None:
        if self.bulk_images_prompt_window and self.bulk_images_prompt_window.isVisible():
            self.bulk_images_prompt_window.reload()
            self.bulk_images_prompt_window.activateWindow()
            self.bulk_images_prompt_window.raise_()
            return
        window = BulkImagesPromptWindow()
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.send_listed_requested.connect(self.enqueue_bulk_images_prompts)
        window.destroyed.connect(self._clear_bulk_images_prompt_window)
        self.bulk_images_prompt_window = window
        window.show()

    def _clear_bulk_images_prompt_window(self) -> None:
        self.bulk_images_prompt_window = None

    def enqueue_bulk_images_prompts(self, prompts: list[Any], quantity_per_prompt: int = 1) -> None:
        if not prompts:
            QMessageBox.warning(self, "Bulk Images", "No hay prompts activos para enviar.")
            return
        try:
            result = self.bulk_images_service.create_prompts_and_enqueue(
                BulkImagesEnqueueRequest(prompts=list(prompts), quantity_per_prompt=quantity_per_prompt)
            )
        except Exception as exc:
            QMessageBox.critical(self, "Bulk Images", str(exc))
            return

        self.refresh()
        QMessageBox.information(
            self,
            "Bulk Images",
            f"Pack {result.pack_id} creado con {len(result.created_prompt_item_ids)} prompts en cola.",
        )

    def open_anime_v5_maintenance_window(self) -> None:
        if self.anime_v5_maintenance_window and self.anime_v5_maintenance_window.isVisible():
            self.anime_v5_maintenance_window.refresh_all()
            self.anime_v5_maintenance_window.activateWindow()
            self.anime_v5_maintenance_window.raise_()
            return
        window = AnimeV5MaintenanceWindow()
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.catalog_updated.connect(self._refresh_anime_v5_catalog)
        window.destroyed.connect(self._clear_anime_v5_maintenance_window)
        self.anime_v5_maintenance_window = window
        window.show()

    def _clear_anime_v5_maintenance_window(self) -> None:
        self.anime_v5_maintenance_window = None

    def _refresh_anime_v5_catalog(self) -> None:
        self._populate_anime_v5_lists()
        self._populate_anime_v5_reel_selectors()
        self._load_anime_v5_prompts()
        self._populate_anime_v5_fixed_outfits()

    def open_clear_category_images_dialog(self) -> None:
        filters = self.store.fetch_prompt_filters()
        filter_categories = set(filters.get("categories") or [])
        catalog_categories = set(self.waifu_catalog.categories.keys())
        categories = sorted(filter_categories | catalog_categories)
        if not categories:
            QMessageBox.information(
                self,
                "Vaciado de imágenes",
                "No hay categorías disponibles para vaciar.",
            )
            return

        counts = dict(self.store.fetch_category_production_counts())
        dialog = QDialog(self)
        dialog.setWindowTitle("Vaciado de imágenes por categoría")
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel("Selecciona una categoría y borra todas las imágenes creadas para ella.")
        )

        row = QHBoxLayout()
        row.addWidget(QLabel("Categoría:"))
        combo = QComboBox()
        for category in categories:
            count = counts.get(category, 0)
            combo.addItem(f"{category} ({count})", category)
        row.addWidget(combo)
        layout.addLayout(row)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        cancel_btn = QPushButton("Cancelar")
        confirm_btn = QPushButton("Vaciar imágenes")
        action_row.addWidget(cancel_btn)
        action_row.addWidget(confirm_btn)
        layout.addLayout(action_row)

        cancel_btn.clicked.connect(dialog.reject)
        confirm_btn.clicked.connect(
            lambda: self._confirm_clear_category_images(dialog, combo)
        )

        dialog.exec()

    def _confirm_clear_category_images(self, dialog: QDialog, combo: QComboBox) -> None:
        category = combo.currentData()
        if not category:
            QMessageBox.warning(self, "Vaciado de imágenes", "Selecciona una categoría válida.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirmar vaciado",
            (
                f"¿Seguro que quieres borrar todas las imágenes creadas de '{category}'?\n"
                "Esta acción no se puede deshacer."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        rows = self.store.list_prompt_images_for_category(category=category)
        if not rows:
            QMessageBox.information(
                self,
                "Vaciado de imágenes",
                f"No hay imágenes creadas para la categoría '{category}'.",
            )
            dialog.accept()
            return

        deleted_files = 0
        missing_files = 0
        error_files = 0
        prompt_ids: list[int] = []

        for row in rows:
            prompt_ids.append(int(row["id"]))
            workflow_key = self._workflow_key_from_row(row)
            for key in ("base_image_json", "upscale_image_json"):
                raw = row.get(key)
                if not raw:
                    continue
                try:
                    image_json = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(image_json, dict):
                    continue
                path = build_output_path(image_json, workflow_key=workflow_key)
                try:
                    if path.exists():
                        path.unlink()
                        deleted_files += 1
                    else:
                        missing_files += 1
                except Exception:
                    error_files += 1

        cleared_rows = self.store.delete_prompt_items(prompt_ids=prompt_ids)
        self._schedule_refresh()

        QMessageBox.information(
            self,
            "Vaciado de imágenes",
            (
                f"Categoría '{category}' vaciada.\n"
                f"Archivos borrados: {deleted_files}\n"
                f"Archivos no encontrados: {missing_files}\n"
                f"Filas eliminadas: {cleared_rows}\n"
                f"Errores al borrar archivos: {error_files}"
            ),
        )
        dialog.accept()

    def on_prompt_base_updated(self) -> None:
        self._reload_waifu_catalog()
        self._populate_pack_selectors()
        self._populate_manual_prompt_selectors()

    def _populate_pack_selectors(self) -> None:
        self.pack_category_combo.clear()
        for key, data in self.waifu_catalog.categories.items():
            if not isinstance(data, dict):
                print(f"[WARN] Categoría inválida en catálogo: {key}={data!r}")
                continue
            if not data.get("enabled", True):
                continue
            label = str(data.get("label", key))
            kind = str(data.get("kind", "category"))
            if kind == "character":
                label = f"{label} [Personaje]"
            self.pack_category_combo.addItem(label, key)

        self.pack_variant_combo.clear()
        for key in self.app_config.variants.keys():
            self.pack_variant_combo.addItem(key, key)

        self.pack_combination_combo.clear()
        self.pack_combination_combo.addItem("Sin combinación", None)
        for key, combo in (self.waifu_catalog.combinations or {}).items():
            if isinstance(combo, dict):
                label = str(combo.get("label", key))
            elif isinstance(combo, list):
                label = key
            else:
                continue
            self.pack_combination_combo.addItem(label, key)

        if self.pack_category_combo.count() == 0:
            self.pack_generate_btn.setEnabled(False)

        self._populate_reel_selectors()

    def _populate_manual_prompt_selectors(self) -> None:
        current_category = self.manual_prompt_category_combo.currentData()
        current_variant = self.manual_prompt_variant_combo.currentData()
        current_ratio = self.manual_prompt_ratio_combo.currentData()

        self.manual_prompt_category_combo.blockSignals(True)
        self.manual_prompt_category_combo.clear()
        for key, data in self.waifu_catalog.categories.items():
            if not isinstance(data, dict):
                continue
            if not data.get("enabled", True):
                continue
            label = str(data.get("label", key))
            kind = str(data.get("kind", "category"))
            if kind == "character":
                label = f"{label} [Personaje]"
            self.manual_prompt_category_combo.addItem(label, key)
        if current_category:
            idx = self.manual_prompt_category_combo.findData(current_category)
            if idx >= 0:
                self.manual_prompt_category_combo.setCurrentIndex(idx)
        self.manual_prompt_category_combo.blockSignals(False)

        self.manual_prompt_variant_combo.clear()
        for key in self.app_config.variants.keys():
            self.manual_prompt_variant_combo.addItem(key, key)
        if current_variant:
            idx = self.manual_prompt_variant_combo.findData(current_variant)
            if idx >= 0:
                self.manual_prompt_variant_combo.setCurrentIndex(idx)

        self._update_manual_prompt_ratios()
        if current_ratio:
            idx = self.manual_prompt_ratio_combo.findData(current_ratio)
            if idx >= 0:
                self.manual_prompt_ratio_combo.setCurrentIndex(idx)
        self._sync_manual_prompt_refiner_label()

    def _update_manual_prompt_ratios(self) -> None:
        category_key = self.manual_prompt_category_combo.currentData()
        ratios: list[str] = []
        if category_key:
            cat = self.waifu_catalog.categories.get(str(category_key), {})
            if isinstance(cat, dict):
                ratios = list(cat.get("allowed_ratios") or [])
        if not ratios:
            ratios = list(self.app_config.ratios.keys()) or ["1:1"]

        current_ratio = self.manual_prompt_ratio_combo.currentData()
        self.manual_prompt_ratio_combo.blockSignals(True)
        self.manual_prompt_ratio_combo.clear()
        for ratio in ratios:
            self.manual_prompt_ratio_combo.addItem(ratio, ratio)
        if current_ratio:
            idx = self.manual_prompt_ratio_combo.findData(current_ratio)
            if idx >= 0:
                self.manual_prompt_ratio_combo.setCurrentIndex(idx)
        self.manual_prompt_ratio_combo.blockSignals(False)

    def _sync_manual_prompt_refiner_label(self) -> None:
        current = self.manual_prompt_checkpoint_combo.currentData()
        self.manual_prompt_refiner_label.setText(str(current) if current else "—")

    def _populate_dollimages_groups(self) -> None:
        current_pack = self.dollimages_group_combo.currentData()
        current_reel = self.dollimages_reel_group_combo.currentData()
        rows = self.store.list_dollimage_prompts(include_disabled=False)
        prompt_groups = sorted({row.group_name.strip() for row in rows if row.group_name.strip()})
        reel_counts = fetch_dollimages_reel_group_counts(typology=None)
        reel_groups = sorted({group for group in reel_counts.keys() if group})
        all_reel_groups = sorted(set(prompt_groups) | set(reel_groups))

        self.dollimages_group_combo.blockSignals(True)
        self.dollimages_group_combo.clear()
        self.dollimages_group_combo.addItem("Todos", None)
        self.dollimages_group_combo.addItem("Sin grupo", "")
        for group in prompt_groups:
            self.dollimages_group_combo.addItem(group, group)
        if current_pack is not None:
            idx = self.dollimages_group_combo.findData(current_pack)
            if idx >= 0:
                self.dollimages_group_combo.setCurrentIndex(idx)
        self.dollimages_group_combo.blockSignals(False)

        total_available = fetch_dollimages_reel_available_count(typology=None, group_name=None)
        self.dollimages_reel_group_combo.blockSignals(True)
        self.dollimages_reel_group_combo.clear()
        self.dollimages_reel_group_combo.addItem(f"Todos ({total_available})", None)
        empty_count = reel_counts.get("", 0)
        self.dollimages_reel_group_combo.addItem(f"Sin grupo ({empty_count})", "")
        for group in all_reel_groups:
            count = reel_counts.get(group, 0)
            label = f"{group} ({count})" if count else group
            self.dollimages_reel_group_combo.addItem(label, group)
        if current_reel is not None:
            idx = self.dollimages_reel_group_combo.findData(current_reel)
            if idx >= 0:
                self.dollimages_reel_group_combo.setCurrentIndex(idx)
        self.dollimages_reel_group_combo.blockSignals(False)
        self._update_dollimages_reel_availability()

    def _populate_reel_selectors(self) -> None:
        self.reel_category_combo.clear()
        for key, data in self.waifu_catalog.categories.items():
            if not isinstance(data, dict):
                continue
            if not data.get("enabled", True):
                continue
            label = str(data.get("label", key))
            kind = str(data.get("kind", "category"))
            if kind == "character":
                label = f"{label} [Personaje]"
            self.reel_category_combo.addItem(label, key)
        self._populate_reel_variants()

    def _populate_reel_variants(self) -> None:
        category = self.reel_category_combo.currentData()
        variants = fetch_variants_for_category(str(category)) if category else []
        current_data = self.reel_variant_combo.currentData()

        self.reel_variant_combo.blockSignals(True)
        self.reel_variant_combo.clear()
        self.reel_variant_combo.addItem("Todas (Variantes)", "__ALL__")
        for variant in variants:
            self.reel_variant_combo.addItem(variant, variant)

        if len(variants) == 1:
            self.reel_variant_combo.setCurrentIndex(1)
        elif current_data:
            idx = self.reel_variant_combo.findData(current_data)
            if idx >= 0:
                self.reel_variant_combo.setCurrentIndex(idx)

        self.reel_variant_combo.setEnabled(len(variants) > 1)
        self.reel_variant_combo.blockSignals(False)

    def _update_dollimages_reel_availability(self) -> None:
        group_name = self.dollimages_reel_group_combo.currentData()
        typology = self.dollimages_reel_typology_combo.currentData()
        available = fetch_dollimages_reel_available_count(
            typology=typology,
            group_name=group_name,
        )
        self.dollimages_reel_available_label.setText(str(available))

    def _update_nsfw_controls(self) -> None:
        combination_key = self.pack_combination_combo.currentData()
        is_nsfw = combination_key == "nsfw"
        self.pack_nsfw_tag_label.setVisible(is_nsfw)
        self.pack_nsfw_tag_spin.setVisible(is_nsfw)

    def _populate_checkpoint_selectors(self) -> None:
        service = CheckpointService()
        models = service.list_available()
        default_base, default_refiner = service.get_default_checkpoints()
        anime_default_base, anime_default_refiner = service.get_default_checkpoints(
            workflow_key="anime_v5", mapping_key="comfyui_workflow_anime_v5"
        )

        def fill_combo(combo: QComboBox, default_value: str | None) -> None:
            combo.clear()
            if not models:
                combo.addItem("Sin modelos detectados", None)
                combo.setEnabled(False)
                return

            combo.setEnabled(True)
            for name in models:
                combo.addItem(name, name)

            if default_value:
                idx = combo.findData(default_value)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        fill_combo(self.pack_checkpoint_base_combo, default_base)
        fill_combo(self.pack_checkpoint_refiner_combo, default_refiner)
        fill_combo(self.dollimages_checkpoint_combo, default_base)
        fill_combo(self.dollimages_manual_checkpoint_combo, default_base)
        fill_combo(self.manual_prompt_checkpoint_combo, default_base)
        fill_combo(self.anime_v5_checkpoint_base_combo, anime_default_base)
        fill_combo(self.anime_v5_checkpoint_refiner_combo, anime_default_refiner)
        self._sync_manual_prompt_refiner_label()



    def _populate_anime_v5_reel_selectors(self) -> None:
        lists = self.store.list_anime_character_lists()
        current_list = self.anime_v5_reel_list_combo.currentData()
        self.anime_v5_reel_list_combo.blockSignals(True)
        self.anime_v5_reel_list_combo.clear()
        self.anime_v5_reel_list_combo.addItem("Todas", None)
        for list_name in sorted(lists):
            self.anime_v5_reel_list_combo.addItem(list_name, list_name)
        if current_list:
            idx = self.anime_v5_reel_list_combo.findData(current_list)
            if idx >= 0:
                self.anime_v5_reel_list_combo.setCurrentIndex(idx)
        self.anime_v5_reel_list_combo.blockSignals(False)
        self._populate_anime_v5_reel_characters()

    def _populate_anime_v5_reel_characters(self) -> None:
        lists = self.store.list_anime_character_lists()
        list_name = self.anime_v5_reel_list_combo.currentData()
        characters = lists.get(str(list_name), []) if list_name else sorted({c for values in lists.values() for c in values})
        current_character = self.anime_v5_reel_character_combo.currentData()
        self.anime_v5_reel_character_combo.blockSignals(True)
        self.anime_v5_reel_character_combo.clear()
        self.anime_v5_reel_character_combo.addItem("Aleatorio / todos", None)
        for character in characters:
            self.anime_v5_reel_character_combo.addItem(character, character)
        if current_character:
            idx = self.anime_v5_reel_character_combo.findData(current_character)
            if idx >= 0:
                self.anime_v5_reel_character_combo.setCurrentIndex(idx)
        self.anime_v5_reel_character_combo.blockSignals(False)

    def generate_anime_v5_reel(self) -> None:
        list_name = self.anime_v5_reel_list_combo.currentData()
        character = self.anime_v5_reel_character_combo.currentData()
        quantity_value = int(self.anime_v5_reel_quantity_spin.value())
        image_count = quantity_value if quantity_value > 0 else None
        seconds_per_image = float(self.anime_v5_reel_seconds_spin.value())
        transition_seconds = float(self.anime_v5_reel_transition_spin.value())
        fade_out = self.anime_v5_reel_fade_out_checkbox.isChecked()
        include_nsfw = self.anime_v5_reel_include_nsfw_checkbox.isChecked()
        try:
            result = self.reel_service.create_anime_v5_reel(
                list_name=list_name,
                character=character,
                image_count=image_count,
                seconds_per_image=seconds_per_image,
                transition_seconds=transition_seconds,
                fade_out=fade_out,
                include_nsfw=include_nsfw,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Reel Anime V5", str(exc))
            return
        self.refresh()
        QMessageBox.information(
            self,
            "Reel Anime V5",
            f"Reel creado con {result.image_count} imágenes.\n{result.video_path}",
        )
        try:
            open_folder_and_select(result.video_path)
        except Exception as exc:
            QMessageBox.critical(self, "Reel Anime V5", f"No se pudo abrir la carpeta: {exc}")

    def _populate_anime_v5_lists(self) -> None:
        current = self.anime_v5_list_combo.currentText().strip()
        selected_lists = {
            item.data(Qt.UserRole)
            for item in self.anime_v5_list_selection.selectedItems()
            if item.data(Qt.UserRole)
        }
        self._anime_v5_character_lists = self.store.list_anime_character_lists(include_descriptions=True)
        self.anime_v5_list_combo.blockSignals(True)
        self.anime_v5_list_selection.blockSignals(True)
        self.anime_v5_list_combo.clear()
        self.anime_v5_list_selection.clear()
        for list_name in sorted(self._anime_v5_character_lists):
            self.anime_v5_list_combo.addItem(list_name, list_name)
            self.anime_v5_list_selection.addItem(list_name)
            item = self.anime_v5_list_selection.item(self.anime_v5_list_selection.count() - 1)
            item.setData(Qt.UserRole, list_name)
            if list_name in selected_lists:
                item.setSelected(True)
        if current:
            idx = self.anime_v5_list_combo.findText(current)
            if idx >= 0:
                self.anime_v5_list_combo.setCurrentIndex(idx)
            else:
                self.anime_v5_list_combo.setEditText(current)
        self.anime_v5_list_combo.blockSignals(False)
        self.anime_v5_list_selection.blockSignals(False)
        self._load_anime_v5_list_from_combo()

    def _load_anime_v5_list_from_combo(self) -> None:
        list_name = self.anime_v5_list_combo.currentText().strip()
        characters = getattr(self, "_anime_v5_character_lists", {}).get(list_name)
        if characters:
            self.anime_v5_characters_input.setPlainText("\n".join(characters))
        self._populate_anime_v5_single_character_options()

    def _anime_v5_character_label(self, value: str) -> str:
        raw = str(value).strip()
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                name = str(data.get("name") or "").strip()
                if name:
                    return name
        return raw

    def _active_anime_v5_generation_list_for_character_filter(self) -> str | None:
        selected = self._selected_anime_v5_generation_lists()
        if len(selected) == 1:
            return selected[0]
        return None

    def _populate_anime_v5_single_character_options(self) -> None:
        current_character = self.anime_v5_single_character_combo.currentData()
        list_name = self._active_anime_v5_generation_list_for_character_filter()
        characters = self._anime_v5_characters_for_generation(
            list_name,
            self.anime_v5_list_combo.currentText().strip(),
        ) if list_name else []

        self.anime_v5_single_character_combo.blockSignals(True)
        self.anime_v5_single_character_combo.clear()
        self.anime_v5_single_character_combo.addItem("Todos", None)
        for character in characters:
            label = self._anime_v5_character_label(character)
            self.anime_v5_single_character_combo.addItem(label, character)
        if current_character:
            idx = self.anime_v5_single_character_combo.findData(current_character)
            if idx >= 0:
                self.anime_v5_single_character_combo.setCurrentIndex(idx)
        self.anime_v5_single_character_combo.setEnabled(bool(list_name and characters))
        self.anime_v5_single_character_combo.blockSignals(False)

    def _anime_v5_characters_from_editor(self) -> list[str]:
        return [
            line.strip()
            for line in self.anime_v5_characters_input.toPlainText().splitlines()
            if line.strip()
        ]

    def _anime_v5_characters_for_generation(self, list_name: str, active_list_name: str) -> list[str]:
        catalog_lists = self.store.list_anime_character_lists(include_descriptions=True)
        self._anime_v5_character_lists = catalog_lists
        catalog_characters = list(catalog_lists.get(list_name, []))
        if catalog_characters:
            return catalog_characters
        if list_name == active_list_name:
            return self._anime_v5_characters_from_editor()
        return []

    def _selected_anime_v5_generation_lists(self) -> list[str]:
        selected = [
            str(item.data(Qt.UserRole) or item.text()).strip()
            for item in self.anime_v5_list_selection.selectedItems()
            if str(item.data(Qt.UserRole) or item.text()).strip()
        ]
        if selected:
            return selected
        current = self.anime_v5_list_combo.currentText().strip()
        return [current] if current else []

    def _select_all_anime_v5_lists(self) -> None:
        for row in range(self.anime_v5_list_selection.count()):
            self.anime_v5_list_selection.item(row).setSelected(True)

    def save_anime_v5_character_list(self) -> None:
        list_name = self.anime_v5_list_combo.currentText().strip()
        characters = [line.strip() for line in self.anime_v5_characters_input.toPlainText().splitlines() if line.strip()]
        if not list_name:
            QMessageBox.warning(self, "Anime V5", "El nombre de la lista es obligatorio.")
            return
        if not characters:
            QMessageBox.warning(self, "Anime V5", "Añade al menos un personaje a la lista.")
            return
        saved = self.store.save_anime_character_list(list_name=list_name, characters=characters)
        self._populate_anime_v5_lists()
        self._populate_anime_v5_reel_selectors()
        self.anime_v5_list_combo.setEditText(list_name)
        QMessageBox.information(self, "Anime V5", f"Lista guardada con {saved} personajes.")

    def _populate_anime_v5_fixed_outfits(self) -> None:
        current = self.anime_v5_fixed_outfit_combo.currentText().strip()
        self.anime_v5_fixed_outfit_combo.blockSignals(True)
        self.anime_v5_fixed_outfit_combo.clear()
        self.anime_v5_fixed_outfit_combo.addItem("Aleatorio", "")
        try:
            outfits = load_anime_v5_prompt_options().get("outfits", [])
        except Exception:
            outfits = []
        for outfit in outfits:
            self.anime_v5_fixed_outfit_combo.addItem(outfit, outfit)
        if current and current != "Aleatorio":
            idx = self.anime_v5_fixed_outfit_combo.findText(current)
            if idx >= 0:
                self.anime_v5_fixed_outfit_combo.setCurrentIndex(idx)
            else:
                self.anime_v5_fixed_outfit_combo.setEditText(current)
        self.anime_v5_fixed_outfit_combo.blockSignals(False)

    def _selected_anime_v5_fixed_outfit(self) -> str | None:
        outfit = self.anime_v5_fixed_outfit_combo.currentText().strip()
        if not outfit or outfit == "Aleatorio":
            data = self.anime_v5_fixed_outfit_combo.currentData()
            outfit = str(data or "").strip()
        return outfit or None

    def apply_anime_v5_generator_template(self) -> None:
        if not self.anime_v5_prompt_title_input.text().strip():
            self.anime_v5_prompt_title_input.setText("Generador Anime V5 SDXL")
        try:
            prompt_options = load_anime_v5_prompt_options()
            prompt_selection = choose_anime_v5_prompt_selection(
                self.anime_generation_service.rng,
                prompt_options,
                fixed_outfit=self._selected_anime_v5_fixed_outfit(),
                manual_outfit_text=self.anime_v5_manual_outfit_input.text().strip(),
            )
            prompt_text = fill_anime_v5_option_tokens(DEFAULT_TEMPLATE, prompt_selection)
        except Exception as exc:
            QMessageBox.critical(self, "Anime V5", str(exc))
            return
        self.anime_v5_prompt_input.setPlainText(prompt_text)

    def _load_anime_v5_prompts(self) -> None:
        self._anime_v5_prompt_templates = self.store.list_anime_prompts()
        self._filter_anime_v5_prompts()

    def open_anime_v5_prompt_picker(self) -> None:
        self._load_anime_v5_prompts()
        self._populate_anime_v5_fixed_outfits()
        self.anime_v5_prompt_picker_dialog.show()
        self.anime_v5_prompt_picker_dialog.raise_()
        self.anime_v5_prompt_picker_dialog.activateWindow()

    def _filter_anime_v5_prompts(self) -> None:
        query = self.anime_v5_prompt_search_input.text().strip().lower()
        rows = []
        for prompt in getattr(self, "_anime_v5_prompt_templates", []):
            haystack = f"{prompt.get('title', '')} {prompt.get('prompt_text', '')}".lower()
            if query and query not in haystack:
                continue
            rows.append(prompt)
        self.anime_v5_prompt_table.setRowCount(len(rows))
        for row_idx, prompt in enumerate(rows):
            title_item = QTableWidgetItem(str(prompt.get("title", "")))
            title_item.setData(Qt.UserRole, prompt)
            prompt_item = QTableWidgetItem(str(prompt.get("prompt_text", "")))
            prompt_item.setData(Qt.UserRole, prompt)
            self.anime_v5_prompt_table.setItem(row_idx, 0, title_item)
            self.anime_v5_prompt_table.setItem(row_idx, 1, prompt_item)
        self.anime_v5_prompt_count_label.setText(str(len(rows)))
        if rows:
            self.anime_v5_prompt_table.selectRow(0)

    def _selected_anime_v5_prompt(self) -> dict[str, object] | None:
        selected = self.anime_v5_prompt_table.selectionModel().selectedRows()
        if not selected:
            return None
        item = self.anime_v5_prompt_table.item(selected[0].row(), 0)
        data = item.data(Qt.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _apply_selected_anime_v5_prompt(self) -> None:
        prompt = self._selected_anime_v5_prompt()
        if not prompt:
            QMessageBox.warning(self, "Anime V5", "Selecciona un prompt.")
            return
        self.anime_v5_prompt_title_input.setText(str(prompt.get("title", "")))
        self.anime_v5_prompt_input.setPlainText(str(prompt.get("prompt_text", "")))
        self.anime_v5_prompt_picker_dialog.accept()

    def generate_anime_v5(self) -> None:
        list_name = self.anime_v5_list_combo.currentText().strip()
        list_names = self._selected_anime_v5_generation_lists()
        prompt_title = self.anime_v5_prompt_title_input.text().strip()
        prompt_text = self.anime_v5_prompt_input.toPlainText().strip()
        quantity = int(self.anime_v5_quantity_spin.value())
        random_combinations = int(self.anime_v5_random_combinations_spin.value())
        fixed_outfit = self._selected_anime_v5_fixed_outfit()
        manual_outfit_text = self.anime_v5_manual_outfit_input.text().strip()
        checkpoint_base = self.anime_v5_checkpoint_base_combo.currentData()
        checkpoint_refiner = self.anime_v5_checkpoint_refiner_combo.currentData()
        content_rating = str(self.anime_v5_content_rating_combo.currentData() or "sfw")
        single_character = self.anime_v5_single_character_combo.currentData()
        add_upskirt_when_skirt = self.anime_v5_upskirt_on_skirt_checkbox.isChecked()
        if not list_names:
            QMessageBox.warning(self, "Anime V5", "Selecciona al menos una lista de anime.")
            return
        if single_character and len(list_names) != 1:
            QMessageBox.warning(
                self,
                "Anime V5",
                "El personaje concreto solo se puede usar con una única lista seleccionada.",
            )
            return
        if not checkpoint_base:
            QMessageBox.warning(self, "Anime V5", "Selecciona un modelo principal.")
            return
        if not checkpoint_refiner:
            QMessageBox.warning(self, "Anime V5", "Selecciona un modelo refined.")
            return

        try:
            results = []
            for selected_list_name in list_names:
                characters = self._anime_v5_characters_for_generation(selected_list_name, list_name)
                if single_character and len(list_names) == 1:
                    characters = [str(single_character)]
                results.append(
                    self.anime_generation_service.create_images_and_enqueue(
                        AnimeGenerationCreate(
                            list_name=selected_list_name,
                            prompt_title=prompt_title,
                            prompt_text=prompt_text,
                            characters=characters,
                            quantity_per_character=quantity,
                            random_combinations=random_combinations,
                            fixed_outfit=fixed_outfit,
                            manual_outfit_text=manual_outfit_text,
                            checkpoint_base=str(checkpoint_base),
                            checkpoint_refiner=str(checkpoint_refiner),
                            content_rating=content_rating,
                            add_upskirt_when_skirt=add_upskirt_when_skirt,
                        )
                    )
                )
        except Exception as exc:
            QMessageBox.critical(self, "Anime V5", str(exc))
            return

        self.refresh()
        pack_ids = ", ".join(str(result.pack_id) for result in results)
        created_count = sum(len(result.created_prompt_item_ids) for result in results)
        QMessageBox.information(
            self,
            "Anime V5",
            f"Packs {pack_ids} creados con {created_count} imágenes en cola.",
        )

    def generate_pack(self) -> None:
        category = self.pack_category_combo.currentData()
        variant = self.pack_variant_combo.currentData()
        quantity = int(self.pack_quantity_spin.value())
        checkpoint_base = self.pack_checkpoint_base_combo.currentData()
        checkpoint_refiner = self.pack_checkpoint_refiner_combo.currentData()
        combination_key = self.pack_combination_combo.currentData()
        manual_feature = self.pack_manual_feature_input.text().strip()
        nsfw_tag_count = None
        if combination_key == "nsfw":
            nsfw_tag_count = int(self.pack_nsfw_tag_spin.value())

        if not category or not variant:
            QMessageBox.warning(self, "Generar Pack", "Selecciona categoría y variante.")
            return

        req = PackCreate(
            category=str(category),
            variant=str(variant),
            requested_n=quantity,
            manual_feature=manual_feature,
            checkpoint_base=str(checkpoint_base) if checkpoint_base else None,
            checkpoint_refiner=str(checkpoint_refiner) if checkpoint_refiner else None,
            combination_key=str(combination_key) if combination_key else None,
            nsfw_tag_count=nsfw_tag_count,
        )

        try:
            result = self.pack_service.create_pack_and_enqueue(None, req)
        except Exception as exc:
            QMessageBox.critical(self, "Generar Pack", str(exc))
            return

        self.refresh()
        QMessageBox.information(
            self,
            "Generar Pack",
            f"Pack {result.pack_id} creado con {len(result.created_prompt_item_ids)} items.",
        )

    def generate_manual_prompt(self) -> None:
        category = self.manual_prompt_category_combo.currentData()
        variant = self.manual_prompt_variant_combo.currentData()
        ratio = self.manual_prompt_ratio_combo.currentData()
        quantity = int(self.manual_prompt_quantity_spin.value())
        checkpoint_base = self.manual_prompt_checkpoint_combo.currentData()
        title_raw = self.manual_prompt_title_input.text()
        prompt_raw = self.manual_prompt_text_input.toPlainText()

        if not category:
            QMessageBox.warning(self, "Prompt manual", "Selecciona una categoría.")
            return
        if not variant:
            QMessageBox.warning(self, "Prompt manual", "Selecciona una variante.")
            return
        if not ratio:
            QMessageBox.warning(self, "Prompt manual", "Selecciona un ratio.")
            return
        if not checkpoint_base:
            QMessageBox.warning(self, "Prompt manual", "Selecciona un checkpoint base.")
            return
        if not title_raw.strip():
            QMessageBox.warning(self, "Prompt manual", "El título es obligatorio.")
            return
        if not prompt_raw.strip():
            QMessageBox.warning(self, "Prompt manual", "El prompt no puede estar vacío.")
            return

        req = ManualPromptCreate(
            category=str(category),
            variant=str(variant),
            ratio=str(ratio),
            title=title_raw,
            prompt_text=prompt_raw,
            quantity=quantity,
            checkpoint_base=str(checkpoint_base),
        )

        try:
            result = self.manual_prompt_service.create_manual_prompts_and_enqueue(req)
        except Exception as exc:
            QMessageBox.critical(self, "Prompt manual", str(exc))
            return

        self.refresh()
        QMessageBox.information(
            self,
            "Prompt manual",
            f"Pack {result.pack_id} creado con {len(result.created_prompt_item_ids)} items.",
        )

    def select_dollimages_reference_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen de referencia",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if file_path:
            self.dollimages_reference_input.setText(file_path)

    def select_dollimages_manual_reference_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen de referencia",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if file_path:
            self.dollimages_manual_reference_input.setText(file_path)

    def generate_dollimages_pack(self) -> None:
        typology = self.dollimages_typology_combo.currentData()
        repetitions = int(self.dollimages_iterations_spin.value())
        checkpoint_base = self.dollimages_checkpoint_combo.currentData()
        manual_text = self.dollimages_manual_input.text().strip()
        reference_image = self.dollimages_reference_input.text().strip()
        group_name = self.dollimages_group_combo.currentData()
        faceswap_enabled = self.dollimages_faceswap_check.isChecked()
        workflow_key = self.dollimages_workflow_combo.currentData()
        ratio = self.dollimages_ratio_combo.currentData()

        if not typology:
            QMessageBox.warning(self, "Crear Pack Dollimages", "Selecciona una tipología.")
            return
        if workflow_key == "dollimages" and faceswap_enabled and not reference_image:
            QMessageBox.warning(self, "Crear Pack Dollimages", "Selecciona una imagen de referencia.")
            return
        if workflow_key == "dollimages" and not checkpoint_base:
            QMessageBox.warning(self, "Crear Pack Dollimages", "Selecciona un checkpoint base.")
            return

        req = DollimagesPackCreate(
            typology=str(typology),
            repetitions=repetitions,
            workflow_key=str(workflow_key),
            ratio=str(ratio or "3:4"),
            manual_text=manual_text,
            checkpoint_base=str(checkpoint_base) if checkpoint_base else None,
            reference_image=reference_image,
            group_name=str(group_name) if group_name is not None else None,
            faceswap_enabled=faceswap_enabled,
        )

        try:
            result = self.dollimages_pack_service.create_pack_and_enqueue(None, req)
        except Exception as exc:
            QMessageBox.critical(self, "Crear Pack Dollimages", str(exc))
            return

        self.refresh()
        QMessageBox.information(
            self,
            "Crear Pack Dollimages",
            f"Pack {result.pack_id} creado con {len(result.created_prompt_item_ids)} items.",
        )

    def generate_dollimages_manual_prompt(self) -> None:
        typology = self.dollimages_manual_typology_combo.currentData()
        repetitions = int(self.dollimages_manual_repetitions_spin.value())
        checkpoint_base = self.dollimages_manual_checkpoint_combo.currentData()
        reference_image = self.dollimages_manual_reference_input.text().strip()
        title_raw = self.dollimages_manual_title_input.text()
        prompt_raw = self.dollimages_manual_prompt_text_input.toPlainText()
        faceswap_enabled = self.dollimages_manual_faceswap_check.isChecked()
        workflow_key = self.dollimages_manual_workflow_combo.currentData()
        ratio = self.dollimages_manual_ratio_combo.currentData()

        if not typology:
            QMessageBox.warning(self, "Prompt manual Dollimages", "Selecciona una tipología.")
            return
        if workflow_key == "dollimages" and faceswap_enabled and not reference_image:
            QMessageBox.warning(
                self, "Prompt manual Dollimages", "Selecciona una imagen de referencia."
            )
            return
        if workflow_key == "dollimages" and not checkpoint_base:
            QMessageBox.warning(
                self, "Prompt manual Dollimages", "Selecciona un checkpoint base."
            )
            return
        if not title_raw.strip():
            QMessageBox.warning(self, "Prompt manual Dollimages", "El título es obligatorio.")
            return
        if not prompt_raw.strip():
            QMessageBox.warning(self, "Prompt manual Dollimages", "El prompt no puede estar vacío.")
            return

        req = DollimagesManualPromptCreate(
            typology=str(typology),
            repetitions=repetitions,
            title=title_raw,
            prompt_text=prompt_raw,
            workflow_key=str(workflow_key),
            ratio=str(ratio or "3:4"),
            checkpoint_base=str(checkpoint_base) if checkpoint_base else None,
            reference_image=reference_image,
            faceswap_enabled=faceswap_enabled,
        )

        try:
            result = self.dollimages_manual_prompt_service.create_manual_prompts_and_enqueue(req)
        except Exception as exc:
            QMessageBox.critical(self, "Prompt manual Dollimages", str(exc))
            return

        self.refresh()
        QMessageBox.information(
            self,
            "Prompt manual Dollimages",
            f"Pack {result.pack_id} creado con {len(result.created_prompt_item_ids)} items.",
        )

    def open_image2vid_dialog(self) -> None:
        self._set_image2vid_source_from_current_selection(show_warning=False)
        self._update_image2vid_labels()
        self.image2vid_dialog.show()

    def open_undress_dialog(self) -> None:
        self._set_undress_source_from_current_selection(show_warning=False)
        self._update_undress_prompt()
        self.undress_dialog.show()

    def _selected_undress_garments(self) -> list[str]:
        return [
            self.undress_garment_list.item(index).text()
            for index in range(self.undress_garment_list.count())
            if self.undress_garment_list.item(index).checkState() == Qt.Checked
        ]

    def _update_undress_prompt(self, _item: QListWidgetItem | None = None) -> None:
        garments = self._selected_undress_garments()
        self.undress_prompt_preview.setPlainText(
            build_undress_prompt(garments)
        )
        seconds, frames = calculate_undress_duration(garments)
        self.undress_format_label.setText(
            f"Formato: 480x768 · {frames} frames · {UNDRESS_FPS} fps · {seconds:g} s"
        )

    def _set_undress_source_from_current_selection(self, show_warning: bool = True) -> None:
        source = self._selected_image2vid_source_from_browser()
        self.undress_selected_source = source
        if source:
            self.undress_source_label.setText(
                f"[{source['source_category']}] #{source['prompt_id']} - {source['title']}"
            )
            return
        self.undress_source_label.setText("Sin imagen seleccionada")
        if show_warning:
            QMessageBox.warning(
                self,
                "Undress",
                "Selecciona en la cola un prompt con una imagen generada disponible.",
            )

    def generate_undress(self) -> None:
        source = getattr(self, "undress_selected_source", None) or {}
        if not source.get("local_path"):
            QMessageBox.warning(self, "Undress", "Debes seleccionar una imagen local de la cola.")
            return

        garments = self._selected_undress_garments()
        prompt = build_undress_prompt(garments)
        seconds, length_frames = calculate_undress_duration(garments)
        source_category = str(source.get("source_category") or "waifu")
        source_prompt_id = int(source.get("prompt_id") or 0)
        req = ImageToVideoCreate(
            source_category=source_category,
            source_prompt_id=source_prompt_id,
            source_url=str(source.get("url") or "").strip(),
            source_image=str(source.get("local_path") or "").strip(),
            title=f"Undress {source_category} #{source_prompt_id}",
            prompt_text=prompt,
            negative_text=IMAGE2VID_MIN_NEGATIVE_PROMPT,
            ratio="5:8",
            width=480,
            height=768,
            seconds=seconds,
            fps=UNDRESS_FPS,
            length_frames=length_frames,
        )
        try:
            result = self.image2vid_service.create_and_enqueue(req, workflow_key="undress")
            QMessageBox.information(
                self,
                "Undress",
                f"Vídeo en cola. Pack #{result.pack_id} · Prompt #{result.created_prompt_item_ids[0]}",
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo encolar Undress\n{exc}")

    def _image2vid_ratio_dimensions(self, ratio: str) -> tuple[int, int]:
        mapping = {
            "1:1": (720, 720),
            "4:5": (576, 720),
            "9:16": (480, 848),
            "16:9": (848, 480),
        }
        return mapping.get(ratio, (720, 720))

    def _compute_image2vid_length(self, *, seconds: float, fps: int = 32, interpolation_multiplier: int = 2) -> int:
        base_frames = int(round((seconds * fps) / max(interpolation_multiplier, 1)))
        return max(base_frames, 1)

    def _update_image2vid_labels(self) -> None:
        ratio = str(self.image2vid_ratio_combo.currentData() or "1:1")
        width, height = self._image2vid_ratio_dimensions(ratio)
        seconds = float(self.image2vid_seconds_spin.value())
        length_frames = self._compute_image2vid_length(seconds=seconds)
        self.image2vid_size_label.setText(f"Tamaño: {width}x{height}")
        self.image2vid_frames_label.setText(f"Frames Wan: {length_frames}")


    def _selected_image2vid_source_from_browser(self) -> dict[str, Any] | None:
        pid = self._selected_prompt_id()
        if pid is None:
            return None

        media = self.store.get_prompt_item_media(pid)
        if not media:
            return None

        base = json.loads(media["base_image_json"]) if media.get("base_image_json") else None
        upscale = json.loads(media["upscale_image_json"]) if media.get("upscale_image_json") else None
        image_json = upscale or base
        if not image_json:
            return None

        workflow_key = self._workflow_key_from_row(media)
        image_path = build_output_path(image_json, workflow_key=workflow_key)
        if not image_path.exists():
            return None

        meta = {}
        if media.get("meta_json"):
            try:
                decoded_meta = json.loads(media["meta_json"])
            except json.JSONDecodeError:
                decoded_meta = {}
            if isinstance(decoded_meta, dict):
                meta = decoded_meta

        title = str(media.get("title") or "").strip() or f"Prompt {pid}"
        source_category = str(meta.get("category") or meta.get("workflow") or workflow_key or "waifu")
        return {
            "prompt_id": pid,
            "source_category": source_category,
            "category": source_category,
            "variant": str(meta.get("combo", {}).get("variant") or meta.get("dollimages_typology") or "?"),
            "url": "",
            "local_path": str(image_path),
            "title": title,
        }

    def _set_image2vid_source_from_current_selection(self, show_warning: bool = True) -> None:
        option = self._selected_image2vid_source_from_browser()
        if not option:
            if show_warning:
                QMessageBox.warning(
                    self,
                    "Image2Vid",
                    "Selecciona en el browse principal un prompt con imagen generada disponible.",
                )
            self.image2vid_selected_source = None
            self._update_image2vid_source_label()
            return

        self.image2vid_selected_source = option
        self._update_image2vid_source_label()

    def _populate_image2vid_sources(self) -> None:
        current = self.image2vid_selected_source or {}
        current_prompt_id = current.get("prompt_id") if isinstance(current, dict) else None
        rows = self.store.fetch_prompts(limit=300, status="DONE")

        options: list[dict[str, Any]] = []
        for row in rows:
            meta_raw = row.get("meta_json")
            if not meta_raw:
                continue
            try:
                meta = json.loads(meta_raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(meta, dict):
                continue

            waifu_urls = [
                str(image.get("url") or "").strip()
                for image in meta.get("waifu_cloudinary_images", [])
                if isinstance(image, dict) and str(image.get("url") or "").strip()
            ]
            waifu_url = str(meta.get("waifu_cloudinary_url") or "").strip()
            if waifu_url and waifu_url not in waifu_urls:
                waifu_urls.insert(0, waifu_url)
            doll_url = str(meta.get("cloudinary_url") or "").strip()
            prompt_id = int(row.get("id") or 0)
            title = str(row.get("title") or "").strip() or f"Prompt {prompt_id}"
            for image_index, current_waifu_url in enumerate(waifu_urls, start=1):
                options.append(
                    {
                        "prompt_id": prompt_id,
                        "source_category": "waifu",
                        "category": str(meta.get("category") or meta.get("workflow") or "waifu"),
                        "variant": str(meta.get("combo", {}).get("variant") or meta.get("dollimages_typology") or "?"),
                        "url": current_waifu_url,
                        "title": f"{title} #{image_index}" if len(waifu_urls) > 1 else title,
                    }
                )
            if doll_url:
                options.append(
                    {
                        "prompt_id": prompt_id,
                        "source_category": "dollimages",
                        "category": str(meta.get("category") or meta.get("workflow") or "dollimages"),
                        "variant": str(meta.get("combo", {}).get("variant") or meta.get("dollimages_typology") or "?"),
                        "url": doll_url,
                        "title": title,
                    }
                )

        self._image2vid_source_options = options
        self._refresh_image2vid_filter_options()
        self._apply_image2vid_source_filters()

        selected: dict[str, Any] | None = None
        if options:
            target_index = 0
            if current_prompt_id is not None:
                for i, option in enumerate(options):
                    if option["prompt_id"] == current_prompt_id and option["source_category"] == current.get("source_category"):
                        target_index = i
                        break
            selected = options[target_index]

        self.image2vid_selected_source = selected
        self._update_image2vid_source_label()

    def _refresh_image2vid_filter_options(self) -> None:
        category = self.image2vid_filter_category_combo.currentData()
        variant = self.image2vid_filter_variant_combo.currentData()

        categories = sorted({str(item.get("category") or "?") for item in self._image2vid_source_options})
        variants = sorted({str(item.get("variant") or "?") for item in self._image2vid_source_options})

        self.image2vid_filter_category_combo.blockSignals(True)
        self.image2vid_filter_category_combo.clear()
        self.image2vid_filter_category_combo.addItem("Todas", None)
        for value in categories:
            self.image2vid_filter_category_combo.addItem(value, value)
        self.image2vid_filter_category_combo.blockSignals(False)

        self.image2vid_filter_variant_combo.blockSignals(True)
        self.image2vid_filter_variant_combo.clear()
        self.image2vid_filter_variant_combo.addItem("Todas", None)
        for value in variants:
            self.image2vid_filter_variant_combo.addItem(value, value)
        self.image2vid_filter_variant_combo.blockSignals(False)

        category_index = self.image2vid_filter_category_combo.findData(category)
        self.image2vid_filter_category_combo.setCurrentIndex(category_index if category_index >= 0 else 0)
        variant_index = self.image2vid_filter_variant_combo.findData(variant)
        self.image2vid_filter_variant_combo.setCurrentIndex(variant_index if variant_index >= 0 else 0)

    def _apply_image2vid_source_filters(self) -> None:
        selected_category = self.image2vid_filter_category_combo.currentData()
        selected_variant = self.image2vid_filter_variant_combo.currentData()
        selected = self.image2vid_selected_source or {}

        filtered_options = [
            option for option in self._image2vid_source_options
            if (not selected_category or option.get("category") == selected_category)
            and (not selected_variant or option.get("variant") == selected_variant)
        ]
        self._image2vid_filtered_source_options = filtered_options

        self.image2vid_source_table.setRowCount(0)
        for option in filtered_options:
            row_index = self.image2vid_source_table.rowCount()
            self.image2vid_source_table.insertRow(row_index)
            self.image2vid_source_table.setItem(row_index, 0, QTableWidgetItem(str(option["prompt_id"])))
            self.image2vid_source_table.setItem(row_index, 1, QTableWidgetItem(str(option["source_category"])))
            self.image2vid_source_table.setItem(row_index, 2, QTableWidgetItem(str(option["title"])))

        self.image2vid_source_count_label.setText(str(len(filtered_options)))

        selected_index = 0
        if self.image2vid_selected_source:
            for idx, option in enumerate(filtered_options):
                if (
                    option["prompt_id"] == selected.get("prompt_id")
                    and option["source_category"] == selected.get("source_category")
                ):
                    selected_index = idx
                    break

        if filtered_options:
            self.image2vid_source_table.selectRow(selected_index)
            self._update_image2vid_source_preview()
        else:
            self.image2vid_source_preview.setPixmap(QPixmap())
            self.image2vid_source_preview.setText("No hay imágenes disponibles con esos filtros")

    def _update_image2vid_source_label(self) -> None:
        source = self.image2vid_selected_source
        if not source:
            self.image2vid_source_label.setText("Sin imagen seleccionada")
            return

        self.image2vid_source_label.setText(
            f"[{source['source_category']}] #{source['prompt_id']} - {source['title']}"
        )

    def open_image2vid_source_picker(self) -> None:
        if not self._image2vid_source_options:
            self._populate_image2vid_sources()
        self._apply_image2vid_source_filters()

        self.image2vid_source_picker_dialog.exec()

    def _get_selected_image2vid_option(self) -> dict[str, Any] | None:
        selected_rows = self.image2vid_source_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row_index = selected_rows[0].row()
        if row_index < 0 or row_index >= len(self._image2vid_filtered_source_options):
            return None
        return self._image2vid_filtered_source_options[row_index]

    def _update_image2vid_source_preview(self) -> None:
        option = self._get_selected_image2vid_option()
        if not option:
            self.image2vid_source_preview.setPixmap(QPixmap())
            self.image2vid_source_preview.setText("Selecciona una imagen")
            return

        image_url = str(option.get("url") or "").strip()
        if not image_url:
            self.image2vid_source_preview.setPixmap(QPixmap())
            self.image2vid_source_preview.setText("Imagen sin URL")
            return

        try:
            with urlopen(image_url, timeout=6) as response:
                image_bytes = response.read()
        except (URLError, TimeoutError, ValueError):
            self.image2vid_source_preview.setPixmap(QPixmap())
            self.image2vid_source_preview.setText("No se pudo cargar la vista previa")
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(image_bytes):
            self.image2vid_source_preview.setPixmap(QPixmap())
            self.image2vid_source_preview.setText("Formato de imagen no soportado")
            return

        scaled = pixmap.scaled(
            self.image2vid_source_preview.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image2vid_source_preview.setPixmap(scaled)
        self.image2vid_source_preview.setText("")

    def _apply_selected_image2vid_source(self) -> None:
        option = self._get_selected_image2vid_option()
        if not option:
            QMessageBox.warning(self, "Image2Vid", "Selecciona una imagen de origen.")
            return

        self.image2vid_selected_source = option
        self._update_image2vid_source_label()
        self.image2vid_source_picker_dialog.accept()

    def _load_image2vid_prompt_templates(self) -> None:
        rows = self.store.list_video_prompt_templates(include_disabled=False)
        self._image2vid_prompt_templates = [
            {"id": row.id, "title": row.title, "prompt_text": row.prompt_text}
            for row in rows
        ]

    def open_image2vid_prompt_picker(self) -> None:
        self._load_image2vid_prompt_templates()
        self._filter_image2vid_prompt_templates()
        self.image2vid_prompt_picker_dialog.exec()

    def _filter_image2vid_prompt_templates(self) -> None:
        query = self.image2vid_prompt_search_input.text().strip().lower()
        self.image2vid_prompt_table.setRowCount(0)

        for template in self._image2vid_prompt_templates:
            haystack = f"{template['title']} {template['prompt_text']}".lower()
            if query and query not in haystack:
                continue
            row = self.image2vid_prompt_table.rowCount()
            self.image2vid_prompt_table.insertRow(row)
            title_item = QTableWidgetItem(str(template["title"]))
            title_item.setData(Qt.UserRole, int(template["id"]))
            self.image2vid_prompt_table.setItem(row, 0, title_item)
            self.image2vid_prompt_table.setItem(row, 1, QTableWidgetItem(str(template["prompt_text"])))

        self.image2vid_prompt_count_label.setText(str(self.image2vid_prompt_table.rowCount()))
        if self.image2vid_prompt_table.rowCount() > 0:
            self.image2vid_prompt_table.selectRow(0)

    def _apply_selected_image2vid_prompt_template(self) -> None:
        selected_rows = self.image2vid_prompt_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Prompts tipo video", "Selecciona un prompt tipo.")
            return

        row = selected_rows[0].row()
        prompt_item = self.image2vid_prompt_table.item(row, 1)
        if not prompt_item:
            return
        self.image2vid_positive_input.setPlainText(prompt_item.text().strip())
        self.image2vid_prompt_picker_dialog.accept()

    def generate_image2vid(self) -> None:
        source_info = self.image2vid_selected_source or {}
        if not isinstance(source_info, dict) or not source_info.get("local_path"):
            QMessageBox.warning(self, "Image2Vid", "Debes seleccionar en el browse principal una imagen de origen local.")
            return

        positive = self.image2vid_positive_input.toPlainText().strip()
        negative = self.image2vid_negative_input.toPlainText().strip()
        if IMAGE2VID_MIN_NEGATIVE_PROMPT not in negative:
            negative = f"{IMAGE2VID_MIN_NEGATIVE_PROMPT}, {negative}" if negative else IMAGE2VID_MIN_NEGATIVE_PROMPT
        if not positive:
            QMessageBox.warning(self, "Image2Vid", "El prompt positivo es obligatorio.")
            return

        ratio = str(self.image2vid_ratio_combo.currentData() or "1:1")
        width, height = self._image2vid_ratio_dimensions(ratio)
        seconds = float(self.image2vid_seconds_spin.value())
        fps = 32
        length_frames = self._compute_image2vid_length(seconds=seconds, fps=fps)

        source_category = str(source_info.get("source_category") or "waifu")
        source_prompt_id = int(source_info.get("prompt_id") or 0)
        source_url = str(source_info.get("url") or "").strip()
        source_image = str(source_info.get("local_path") or "").strip()
        title = self.image2vid_title_input.text().strip() or f"Image2Vid {source_category} #{source_prompt_id}"

        req = ImageToVideoCreate(
            source_category=source_category,
            source_prompt_id=source_prompt_id,
            source_url=source_url,
            source_image=source_image,
            title=title,
            prompt_text=positive,
            negative_text=negative,
            ratio=ratio,
            width=width,
            height=height,
            seconds=seconds,
            fps=fps,
            length_frames=length_frames,
        )

        try:
            result = self.image2vid_service.create_and_enqueue(req)
            QMessageBox.information(
                self,
                "Image2Vid",
                f"Video en cola. Pack #{result.pack_id} · Prompt #{result.created_prompt_item_ids[0]}",
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo encolar image2vid\n{exc}")

    def generate_reel(self) -> None:
        category = self.reel_category_combo.currentData()
        quantity = int(self.reel_quantity_spin.value())
        seconds_per_image = float(self.reel_seconds_spin.value())
        variant = self.reel_variant_combo.currentData()
        fade_out = self.reel_fade_out_checkbox.isChecked()
        social_handle = self.reel_social_input.text().strip() or None
        if variant == "__ALL__":
            variant = None

        if not category:
            QMessageBox.warning(self, "Reel Instagram", "Selecciona una categoría.")
            return

        try:
            result = self.reel_service.create_reel(
                category=str(category),
                variant=str(variant) if variant else None,
                image_count=quantity,
                seconds_per_image=seconds_per_image,
                fade_out=fade_out,
                social_handle=social_handle,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Reel Instagram", str(exc))
            return

        try:
            open_folder_and_select(result.folder)
        except Exception as exc:
            QMessageBox.critical(self, "Reel Instagram", f"No se pudo abrir la carpeta: {exc}")

    def _populate_bulk_youtube_category_combo(self) -> None:
        current = self.bulk_youtube_category_combo.currentData() if hasattr(self, "bulk_youtube_category_combo") else None
        self.bulk_youtube_category_combo.clear()
        for row in get_store().list_bulk_youtube_categories():
            category = str(row.get("category") or "").strip()
            count = int(row.get("available_count") or 0)
            if category:
                self.bulk_youtube_category_combo.addItem(f"{category} ({count})", category)
        if current:
            idx = self.bulk_youtube_category_combo.findData(current)
            if idx >= 0:
                self.bulk_youtube_category_combo.setCurrentIndex(idx)

    def open_bulk_youtube_dialog(self) -> None:
        self._populate_bulk_youtube_category_combo()
        self._populate_bulk_youtube_audio_combo()
        self._update_bulk_youtube_plan_label()
        self.bulk_youtube_dialog.show()

    def _update_bulk_youtube_plan_label(self) -> None:
        if not hasattr(self, "bulk_youtube_plan_label"):
            return
        category = self.bulk_youtube_category_combo.currentData()
        audio_filename = self.bulk_youtube_audio_combo.currentData()
        if not category or not audio_filename:
            self.bulk_youtube_plan_label.setText("Selecciona categoría y audio para calcular imágenes necesarias.")
            return
        try:
            plan = self.video_montage_service.calculate_bulk_youtube_plan(
                bulk_category=str(category),
                audio_filename=str(audio_filename),
                image_display_seconds=float(self.bulk_youtube_seconds_spin.value()),
                transition_seconds=float(self.bulk_youtube_transition_spin.value()),
                transition_type=str(self.bulk_youtube_transition_type_combo.currentData() or "fade"),
            )
        except Exception as exc:
            self.bulk_youtube_plan_label.setText(f"No se pudo calcular el plan: {exc}")
            return
        self.bulk_youtube_plan_label.setText(
            f"Audio: {plan.audio_duration_seconds:.1f}s · "
            f"Imagen: {plan.image_display_seconds:.2f}s · "
            f"Transición: {plan.transition_seconds:.2f}s ({self.bulk_youtube_transition_type_combo.currentText()}) · "
            f"Necesitas: {plan.needed_images} imágenes · "
            f"Disponibles en categoría: {plan.available_images}"
        )


    def _populate_bulk_youtube_audio_combo(self) -> None:
        current = self.bulk_youtube_audio_combo.currentData() if hasattr(self, "bulk_youtube_audio_combo") else None
        audio_dir = Path(__file__).resolve().parents[2] / "resources" / "audio_relax"
        audio_files = sorted(path for path in audio_dir.glob("*.mp3") if path.is_file()) if audio_dir.exists() else []

        self.bulk_youtube_audio_combo.clear()
        for audio_path in audio_files:
            self.bulk_youtube_audio_combo.addItem(audio_path.name, audio_path.name)
        if current:
            idx = self.bulk_youtube_audio_combo.findData(current)
            if idx >= 0:
                self.bulk_youtube_audio_combo.setCurrentIndex(idx)
        self.bulk_youtube_generate_btn.setEnabled(bool(audio_files))
        self._update_bulk_youtube_plan_label()

    def generate_bulk_youtube_video(self) -> None:
        if self.bulk_youtube_thread and self.bulk_youtube_thread.isRunning():
            QMessageBox.information(
                self,
                "Vídeo YouTube Bulk Images",
                "Ya hay un vídeo YouTube Bulk Images generándose. Revisa la ventana de progreso.",
            )
            return

        bulk_category = str(self.bulk_youtube_category_combo.currentData() or "").strip()
        audio_filename = self.bulk_youtube_audio_combo.currentData()
        if not bulk_category:
            QMessageBox.warning(self, "Vídeo YouTube Bulk Images", "Indica la categoría Bulk Images.")
            return
        if not audio_filename:
            QMessageBox.warning(
                self,
                "Vídeo YouTube Bulk Images",
                "Añade al menos un MP3 en resources/audio_relax y pulsa Recargar audios.",
            )
            return

        progress_dialog = QDialog(self)
        progress_dialog.setWindowTitle("Progreso vídeo YouTube Bulk Images")
        progress_dialog.setModal(False)
        progress_dialog.setAttribute(Qt.WA_DeleteOnClose, False)
        progress_layout = QVBoxLayout(progress_dialog)
        progress_label = QLabel("Preparando vídeo. Puedes seguir usando la aplicación mientras se renderiza.")
        progress_log = QPlainTextEdit()
        progress_log.setReadOnly(True)
        progress_log.setMinimumSize(620, 260)
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(progress_log)
        progress_dialog.show()
        self.bulk_youtube_progress_dialog = progress_dialog
        self.bulk_youtube_generate_btn.setEnabled(False)

        thread = BulkYoutubeVideoThread(
            self.video_montage_service,
            bulk_category=bulk_category,
            audio_filename=str(audio_filename),
            image_display_seconds=float(self.bulk_youtube_seconds_spin.value()),
            transition_seconds=float(self.bulk_youtube_transition_spin.value()),
            resolution=str(self.bulk_youtube_resolution_combo.currentData() or "4k"),
            transition_type=str(self.bulk_youtube_transition_type_combo.currentData() or "fade"),
        )
        self.bulk_youtube_thread = thread

        def _log_progress(message: str) -> None:
            progress_label.setText(message)
            progress_log.appendPlainText(message)
            progress_log.verticalScrollBar().setValue(progress_log.verticalScrollBar().maximum())

        def _cleanup_thread() -> None:
            self.bulk_youtube_generate_btn.setEnabled(bool(self.bulk_youtube_audio_combo.count()))
            thread.deleteLater()
            if self.bulk_youtube_thread is thread:
                self.bulk_youtube_thread = None

        def _handle_success(result: object) -> None:
            assert isinstance(result, BulkImagesYoutubeVideoResult)
            if self.bulk_youtube_progress_dialog:
                self.bulk_youtube_progress_dialog.close()
                self.bulk_youtube_progress_dialog = None
            QMessageBox.information(
                self,
                "Vídeo YouTube Bulk Images",
                f"Vídeo creado: {result.video_path.name}\n"
                f"Categoría: {result.bulk_category} · Duración: {result.duration_seconds:.1f}s\n"
                f"Imágenes usadas: {len(result.source_images)} · Audio: {result.audio_path.name}",
            )
            try:
                open_folder_and_select(result.video_path)
            except Exception as exc:
                QMessageBox.critical(self, "Vídeo YouTube Bulk Images", f"No se pudo abrir el vídeo: {exc}")

        def _handle_failure(message: str) -> None:
            if self.bulk_youtube_progress_dialog:
                self.bulk_youtube_progress_dialog.close()
                self.bulk_youtube_progress_dialog = None
            QMessageBox.critical(self, "Vídeo YouTube Bulk Images", message)

        thread.progress.connect(_log_progress)
        thread.succeeded.connect(_handle_success)
        thread.failed.connect(_handle_failure)
        thread.finished.connect(_cleanup_thread)
        thread.start()

    def add_video_montage_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Añadir vídeos al montaje",
            "",
            "Vídeos (*.mp4 *.mov *.m4v *.mkv *.webm *.avi)",
        )
        if not file_paths:
            return
        self.video_montage_list.add_video_paths([Path(path) for path in file_paths])

    def remove_selected_video_montage_files(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.video_montage_list.selectedIndexes()},
            reverse=True,
        )
        for row in selected_rows:
            self.video_montage_list.takeItem(row)

    def generate_video_montage(self) -> None:
        source_videos = self.video_montage_list.video_paths()
        if len(source_videos) < 2:
            QMessageBox.warning(self, "Montar Videos", "Añade al menos dos vídeos.")
            return

        ratio = str(self.video_montage_ratio_combo.currentData() or "9:16")
        transition_seconds = float(self.video_montage_transition_spin.value())
        fade_out = self.video_montage_fade_out_checkbox.isChecked()

        try:
            result = self.video_montage_service.create_montage(
                source_videos=source_videos,
                ratio=ratio,
                transition_seconds=transition_seconds,
                fade_out=fade_out,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Montar Videos", str(exc))
            return

        QMessageBox.information(
            self,
            "Montar Videos",
            f"Montaje creado: {result.video_path.name}\n"
            f"Duración: {result.duration_seconds:.1f}s · Ratio: {result.ratio}\n"
            f"Música: {result.audio_path.name if result.audio_path else 'sin música disponible'}",
        )
        try:
            open_folder_and_select(result.video_path)
        except Exception as exc:
            QMessageBox.critical(self, "Montar Videos", f"No se pudo abrir el vídeo: {exc}")

    def generate_dollimages_reel(self) -> None:
        group_name = self.dollimages_reel_group_combo.currentData()
        typology = self.dollimages_reel_typology_combo.currentData()
        quantity = int(self.dollimages_reel_quantity_spin.value())
        seconds_per_image = float(self.dollimages_reel_seconds_spin.value())
        fade_out = self.dollimages_reel_fade_out_checkbox.isChecked()
        overlay_title = self.dollimages_reel_overlay_title_checkbox.isChecked()
        social_handle = self.dollimages_reel_social_input.text().strip() or None

        try:
            result = self.reel_service.create_dollimages_reel(
                typology=str(typology) if typology else None,
                group_name=str(group_name) if group_name is not None else None,
                image_count=quantity,
                seconds_per_image=seconds_per_image,
                fade_out=fade_out,
                overlay_title=overlay_title,
                social_handle=social_handle,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Reel Dollimages", str(exc))
            return

        try:
            open_folder_and_select(result.folder)
        except Exception as exc:
            QMessageBox.critical(self, "Reel Dollimages", f"No se pudo abrir la carpeta: {exc}")

    # -------- Preview helpers --------

    def _toggle_base_preview(self, checked: bool) -> None:
        if self.toggle_preview_action.isChecked() != checked:
            self.toggle_preview_action.blockSignals(True)
            self.toggle_preview_action.setChecked(checked)
            self.toggle_preview_action.blockSignals(False)
        if self.preview_toggle_check.isChecked() != checked:
            self.preview_toggle_check.blockSignals(True)
            self.preview_toggle_check.setChecked(checked)
            self.preview_toggle_check.blockSignals(False)
        self.base_group.setVisible(checked)
        self._update_right_column_visibility()
        self._restart_preview_auto_disable_timer()

    def _restart_preview_auto_disable_timer(self) -> None:
        self._preview_auto_disable_timer.stop()
        if self.preview_toggle_check.isChecked():
            self._preview_auto_disable_timer.start(self.preview_auto_disable_spin.value() * 1000)

    def _auto_disable_base_preview(self) -> None:
        self._toggle_base_preview(False)

    def _toggle_worker_log(self, checked: bool) -> None:
        self.worker_log_group.setVisible(checked)
        self._update_right_column_visibility()
        if checked:
            self._rescale_previews()

    def _update_right_column_visibility(self) -> None:
        show_base = self.toggle_preview_action.isChecked()
        show_log = self.toggle_worker_log_action.isChecked()
        self.base_group.setVisible(show_base)
        self.worker_log_group.setVisible(show_log)
        show_right = show_base or show_log
        self.right_column_widget.setVisible(show_right)
        if show_right:
            self.main_content_layout.setStretch(0, 7)
            self.main_content_layout.setStretch(1, 3)
        else:
            self.main_content_layout.setStretch(0, 10)
            self.main_content_layout.setStretch(1, 0)

    def _set_preview(self, *, which: str, path: Path | None, video_url: str | None = None) -> None:
        if which != "base":
            return

        self._base_path = path
        self._preview_video_url = video_url
        img_label = self.base_image_label
        self._pix_base = None
        self._stop_base_video_preview()
        has_video_preview = bool(video_url)
        self.base_video_play_btn.setEnabled(has_video_preview)
        self.base_video_stop_btn.setEnabled(has_video_preview)

        if video_url:
            self.base_preview_stack.setCurrentWidget(self.base_video_widget)
            self.base_video_player.setSource(QUrl(video_url))
            return

        self.base_preview_stack.setCurrentWidget(self.base_image_label)

        if not path:
            img_label.setText("(sin imagen)")
            img_label.setPixmap(QPixmap())
            return

        if not path.exists():
            img_label.setText("(archivo no existe)")
            img_label.setPixmap(QPixmap())
            return

        pix = QPixmap(str(path))
        if pix.isNull():
            img_label.setText("(no se pudo cargar)")
            img_label.setPixmap(QPixmap())
            return

        self._pix_base = pix

        self._rescale_previews()

    def _inline_operation_widget(self, label_text: str, control: QWidget) -> QWidget:
        widget = QWidget()
        widget.setObjectName("InlineOperationControl")
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        label = QLabel(label_text)
        row.addWidget(label)
        row.addWidget(control, 1)
        return widget

    def _clear_grid_layout(self, grid: QGridLayout) -> None:
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _responsive_column_count(self, available_width: int, preferred_cell_width: int, item_count: int) -> int:
        if item_count <= 0:
            return 1
        columns = max(1, available_width // preferred_cell_width)
        return min(item_count, columns)

    def _relayout_responsive_panels(self) -> None:
        if hasattr(self, "quick_action_buttons"):
            quick_width = max(1, self.quick_actions_layout.geometry().width() or self.width())
            columns = self._responsive_column_count(quick_width, 145, len(self.quick_action_buttons))
            if columns != self._quick_actions_columns:
                self._clear_grid_layout(self.quick_actions_layout)
                for index, button in enumerate(self.quick_action_buttons):
                    self.quick_actions_layout.addWidget(button, index // columns, index % columns)
                for column in range(max(self._quick_actions_columns, columns)):
                    self.quick_actions_layout.setColumnStretch(column, 1 if column < columns else 0)
                self._quick_actions_columns = columns

        if hasattr(self, "operation_widgets"):
            operation_width = max(1, self.operation_layout.geometry().width() or self.width())
            columns = self._responsive_column_count(operation_width, 185, len(self.operation_widgets))
            if columns != self._operation_columns:
                self._clear_grid_layout(self.operation_layout)
                for index, widget in enumerate(self.operation_widgets):
                    self.operation_layout.addWidget(widget, index // columns, index % columns)
                for column in range(max(self._operation_columns, columns)):
                    self.operation_layout.setColumnStretch(column, 1 if column < columns else 0)
                self._operation_columns = columns

    def _rescale_previews(self) -> None:
        if self.base_preview_stack.currentWidget() is self.base_video_widget:
            return
        if self._pix_base and not self._pix_base.isNull():
            target = self.base_image_label.size()
            scaled = self._pix_base.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.base_image_label.setPixmap(scaled)
            self.base_image_label.setText("")
        else:
            if not self.base_image_label.pixmap():
                self.base_image_label.setText("(sin base)")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale_previews()
        self._relayout_responsive_panels()

    # -------- Selection: enable actions + update preview --------

    def update_actions_state(self) -> None:
        pid = self._selected_prompt_id()
        if pid is None:
            self.open_base_action.setEnabled(False)
            self.open_up_action.setEnabled(False)
            self.open_folder_base_action.setEnabled(False)
            self.open_folder_up_action.setEnabled(False)
            self.open_video_action.setEnabled(False)
            self.open_folder_video_action.setEnabled(False)
            self.mark_reel_priority_action.setEnabled(False)
            self.mark_reel_discard_action.setEnabled(False)
            self.clear_reel_flags_action.setEnabled(False)
            self._set_preview(which="base", path=None, video_url=None)
            return

        r = self.store.get_prompt_item_media(pid)
        is_image2vid = bool(r and self._workflow_key_from_row(r) in {"image2vid", "undress"})
        has_base = bool(r and r.get("base_image_json") and not is_image2vid)
        has_up = bool(r and r.get("upscale_image_json"))
        video = self._video_output_from_row(r)

        self.open_base_action.setEnabled(has_base)
        self.open_folder_base_action.setEnabled(has_base)
        self.open_up_action.setEnabled(has_up)
        self.open_folder_up_action.setEnabled(has_up)
        self.open_video_action.setEnabled(video is not None)
        self.open_folder_video_action.setEnabled(video is not None)
        self.mark_reel_priority_action.setEnabled(True)
        self.mark_reel_discard_action.setEnabled(True)
        self.clear_reel_flags_action.setEnabled(True)

        base_path: Path | None = None
        video_url: str | None = None
        if r and is_image2vid:
            video_url = self._video_preview_url_from_row(r, video)
        elif r and r.get("base_image_json"):
            base = json.loads(r["base_image_json"])
            workflow_key = self._workflow_key_from_row(r)
            base_path = build_output_path(base, workflow_key=workflow_key)

        self._set_preview(which="base", path=base_path, video_url=video_url)

    def _video_preview_url_from_row(
        self,
        row: dict[str, Any],
        video: dict[str, Any] | None,
    ) -> str | None:
        return resolve_video_preview_url(row=row, video=video)

    def _on_base_video_status_changed(self, status) -> None:
        if self.base_preview_stack.currentWidget() is not self.base_video_widget:
            return
        if status == QMediaPlayer.EndOfMedia:
            self.base_video_player.setPosition(0)

    def _play_base_video_preview(self) -> None:
        if not self._preview_video_url:
            return
        if self.base_preview_stack.currentWidget() is not self.base_video_widget:
            self.base_preview_stack.setCurrentWidget(self.base_video_widget)
        self.base_video_player.play()

    def _stop_base_video_preview(self) -> None:
        self.base_video_player.stop()
        self.base_video_player.setPosition(0)

    def _show_table_context_menu(self, position) -> None:
        item = self.table.itemAt(position)
        if not item:
            return
        row = item.row()
        self.table.selectRow(row)
        self._sync_current_cell_to_selection()
        self.update_actions_state()

        pid = self._prompt_id_for_row(row)
        if pid is None:
            return

        menu = QMenu(self)
        menu.addAction(self.mark_reel_priority_action)
        menu.addAction(self.mark_reel_discard_action)
        menu.addAction(self.clear_reel_flags_action)
        menu.addSeparator()

        variant_menu = self._build_variant_context_menu(prompt_id=pid)
        if variant_menu:
            menu.addMenu(variant_menu)

        menu.exec(self.table.viewport().mapToGlobal(position))

    def _build_variant_context_menu(self, *, prompt_id: int) -> QMenu | None:
        row = self.store.get_prompt_item(prompt_id)
        if not row:
            return None
        workflow_key = self._workflow_key_from_row(row)
        current_variant = self._extract_variant_from_meta(row.get("meta_json"), workflow_key)

        if workflow_key in {"dollimages", "dollimagesz"}:
            label = "Cambiar tipología"
            options = [
                ("Normal", "normal"),
                ("SFW", "sfw"),
                ("NSFW", "nsfw"),
            ]
        else:
            label = "Cambiar versión"
            options = [(key, key) for key in self.app_config.variants.keys()]

        if not options:
            return None

        menu = QMenu(label, self)
        for text, value in options:
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(value == current_variant)
            action.triggered.connect(
                partial(self._set_prompt_item_variant, prompt_id, value, workflow_key)
            )
        return menu

    def _extract_variant_from_meta(self, meta_json: str | None, workflow_key: str) -> str | None:
        if not meta_json:
            return None
        try:
            meta = json.loads(meta_json)
        except ValueError:
            return None
        if not isinstance(meta, dict):
            return None
        if workflow_key in {"dollimages", "dollimagesz"}:
            typology = meta.get("dollimages_typology")
            if typology:
                return str(typology)
        combo = meta.get("combo", {})
        if isinstance(combo, dict):
            variant = combo.get("variant")
            if variant:
                return str(variant)
        return None

    def _set_prompt_item_variant(self, prompt_id: int, variant: str, workflow_key: str) -> None:
        row = self.store.get_prompt_item(prompt_id)
        current_variant = (
            self._extract_variant_from_meta(row.get("meta_json"), workflow_key) if row else None
        )
        if current_variant == variant:
            return
        self.store.set_prompt_item_variant(
            prompt_id=prompt_id,
            variant=variant,
            workflow_key=workflow_key,
        )
        self._schedule_refresh(resize_columns=False)

    def mark_selected_reel_priority(self) -> None:
        pid = self._selected_prompt_id()
        if pid is None:
            return
        self.store.set_prompt_item_reel_flags(prompt_id=pid, priority=True, discarded=False)
        self._schedule_refresh(resize_columns=False)

    def mark_selected_reel_discarded(self) -> None:
        pid = self._selected_prompt_id()
        if pid is None:
            return
        self.store.set_prompt_item_reel_flags(prompt_id=pid, priority=False, discarded=True)
        self._schedule_refresh(resize_columns=False)

    def clear_selected_reel_flags(self) -> None:
        pid = self._selected_prompt_id()
        if pid is None:
            return
        self.store.set_prompt_item_reel_flags(prompt_id=pid, priority=False, discarded=False)
        self._schedule_refresh(resize_columns=False)

    def open_prompt_dialog_from_item(self, item: QTableWidgetItem) -> None:
        if self.prompt_dialog and self.prompt_dialog.isVisible():
            return

        pid = self._prompt_id_for_row(item.row())
        if pid is None:
            return

        prompt_text = self._fetch_prompt_text(pid)
        backend_status = self._backend_status_for_row(item.row())

        dialog = PromptDetailDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.set_prompt_data(pid, prompt_text or "—", backend_status)
        dialog.copyRequested.connect(self.copy_prompt_to_clipboard)
        dialog.retryRequested.connect(self.retry_selected_prompt)
        dialog.deleteRequested.connect(self.delete_selected_prompt)
        dialog.finished.connect(self._clear_prompt_dialog)
        self.prompt_dialog = dialog
        dialog.show()

    def _clear_prompt_dialog(self) -> None:
        self.prompt_dialog = None

    def _fetch_prompt_text(self, prompt_id: int) -> str | None:
        return self.store.get_prompt_text(prompt_id)

    # -------- Open actions --------

    def start_worker(self) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            return

        self.worker_thread = WorkerThread(
            poll_idle_seconds=1.0,
            delay_seconds=float(self.pause_between_spin.value()),
        )
        self.worker_thread.status.connect(self.on_worker_status)
        self.worker_thread.processed.connect(self.on_worker_processed)
        self.worker_thread.progressed.connect(self.on_worker_progressed)
        self.worker_thread.log.connect(self.append_worker_log)
        self.worker_thread.start()

        self.start_worker_btn.setEnabled(False)
        self.stop_worker_btn.setEnabled(True)
        self.worker_status_label.setText("Worker: STARTING...")

    def stop_worker(self) -> None:
        if not self.worker_thread:
            return
        self.worker_thread.stop()
        self.worker_thread.wait(3000)

        self.start_worker_btn.setEnabled(True)
        self.stop_worker_btn.setEnabled(False)
        self.worker_status_label.setText("Worker: STOPPED")
        self.append_worker_log("[WORKER] STOPPED")

    def _update_worker_delay(self, value: int) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.set_delay_seconds(float(value))

    def on_worker_status(self, s: str) -> None:
        if s == "PAUSED":
            self.worker_status_label.setText("Worker: PAUSADO (cola detenida)")
        elif s == "IDLE":
            self.worker_status_label.setText("Worker: IDLE (sin jobs)")
        elif s == "RUNNING":
            self.worker_status_label.setText("Worker: RUNNING")
        elif s == "ERROR":
            self.worker_status_label.setText("Worker: ERROR")
        else:
            self.worker_status_label.setText(f"Worker: {s}")

    def append_worker_log(self, message: str) -> None:
        if self.worker_log_text.toPlainText().strip() == "—":
            self.worker_log_text.setPlainText(message)
        else:
            self.worker_log_text.appendPlainText(message)

    def clear_worker_log(self) -> None:
        self.worker_log_text.setPlainText("—")

    def on_worker_processed(self) -> None:
        self._schedule_refresh()

    def on_worker_progressed(self) -> None:
        self._schedule_refresh()

    def open_selected(self, mode: str) -> None:
        pid = self._selected_prompt_id()
        if pid is None:
            QMessageBox.warning(self, "Abrir", "Selecciona una fila primero.")
            return

        r = self.store.get_prompt_item_media(pid)
        if not r:
            QMessageBox.warning(self, "Abrir", f"No existe prompt_item {pid}.")
            return

        base = json.loads(r["base_image_json"]) if r.get("base_image_json") else None
        up = json.loads(r["upscale_image_json"]) if r.get("upscale_image_json") else None
        workflow_key = self._workflow_key_from_row(r)
        video = self._video_output_from_row(r)

        try:
            if mode == "base":
                if not base:
                    raise RuntimeError("Este item no tiene base_image_json.")
                open_file(build_output_path(base, workflow_key=workflow_key))

            elif mode == "upscale":
                if not up:
                    raise RuntimeError("Este item no tiene upscale_image_json.")
                open_file(build_output_path(up, workflow_key=workflow_key))

            elif mode == "folder_base":
                if not base:
                    raise RuntimeError("Este item no tiene base_image_json.")
                open_folder_and_select(build_output_path(base, workflow_key=workflow_key))

            elif mode == "folder_upscale":
                if not up:
                    raise RuntimeError("Este item no tiene upscale_image_json.")
                open_folder_and_select(build_output_path(up, workflow_key=workflow_key))

            elif mode in {"video", "folder_video"}:
                if not video:
                    raise RuntimeError("Este item no tiene un video generado.")
                video_path = build_output_path(video, workflow_key=workflow_key)
                if mode == "video":
                    open_file(video_path)
                else:
                    open_folder_and_select(video_path)

            else:
                raise RuntimeError("Modo desconocido.")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _video_output_from_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row or self._workflow_key_from_row(row) not in {"image2vid", "undress"}:
            return None
        return extract_saved_video_output(
            base_media_json=row.get("base_image_json"),
            history_json=row.get("output_json"),
        )

    def closeEvent(self, event) -> None:
        try:
            if self._refresh_timer.isActive():
                self._refresh_timer.stop()
            self._refresh_pending = False
            refresh_worker = self._refresh_worker
            if refresh_worker and refresh_worker.isRunning():
                refresh_worker.requestInterruption()
                refresh_worker.wait(5000)
                if refresh_worker.isRunning():
                    refresh_worker.terminate()
                    refresh_worker.wait(1000)
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.stop()
                self.worker_thread.wait(2000)
                if self.worker_thread.isRunning():
                    self.worker_thread.terminate()
                    self.worker_thread.wait(1000)
            if self.bulk_youtube_thread and self.bulk_youtube_thread.isRunning():
                self.bulk_youtube_thread.wait(2000)
                if self.bulk_youtube_thread.isRunning():
                    self.bulk_youtube_thread.terminate()
                    self.bulk_youtube_thread.wait(1000)
        finally:
            super().closeEvent(event)

    def open_preview_dialog(self, which: str) -> None:
        if which != "base":
            return
        path = self._base_path
        if not path or not path.exists():
            QMessageBox.information(self, "Preview", "No hay imagen disponible para ampliar.")
            return

        title = "Preview Base"
        dlg = ImageViewer(title, path)
        dlg.exec()

    def copy_prompt_to_clipboard(self, prompt_id: int | None = None, prompt_text: str | None = None) -> None:
        prompt = (prompt_text or "").strip()
        if not prompt or prompt == "—":
            pid = prompt_id if prompt_id is not None else self._selected_prompt_id()
            if pid is None:
                QMessageBox.warning(self, "Copiar prompt", "Selecciona un prompt primero.")
                return
            prompt = (self._fetch_prompt_text(pid) or "").strip()

        if not prompt or prompt == "—":
            QMessageBox.warning(self, "Copiar prompt", "No hay prompt para copiar.")
            return

        QApplication.clipboard().setText(prompt)

    def _workflow_key_from_row(self, row: dict[str, Any]) -> str:
        meta_json = row.get("meta_json")
        if not meta_json:
            return "waifu"
        try:
            meta = json.loads(meta_json)
        except ValueError:
            return "waifu"
        return str(meta.get("workflow") or "waifu")

    def _selected_filter_value(self, combo: QComboBox) -> str | None:
        value = combo.currentData()
        if value is None or value == "__ALL__":
            return None
        return str(value)

    def _selected_prompt_id_filter(self) -> int | None:
        raw = self.prompt_id_input.text().strip()
        if not raw:
            return None
        if not raw.isdigit():
            return None
        return int(raw)

    def _selected_datetime_value(self, edit: QDateTimeEdit) -> str | None:
        value = edit.dateTime()
        if value == edit.minimumDateTime():
            return None
        return value.toString("yyyy-MM-dd HH:mm:ss")

    def _selected_sort_order(self) -> str:
        value = self.filter_date_order_combo.currentData()
        if value in {"asc", "desc"}:
            return str(value)
        return "desc"

    def _set_dark_mode(self, enabled: bool) -> None:
        self._dark_mode = enabled
        self._apply_theme()
        if hasattr(self, "table"):
            self._style_table_selection()

    def _apply_theme(self) -> None:
        stylesheet = self._theme_stylesheet(self._dark_mode)
        app = QApplication.instance()
        if app is not None:
            app.setPalette(self._build_palette(self._dark_mode))
            app.setStyleSheet(stylesheet)
        self.setStyleSheet(stylesheet)

    def _build_palette(self, dark: bool) -> QPalette:
        palette = QPalette()
        if dark:
            palette.setColor(QPalette.Window, QColor("#0f172a"))
            palette.setColor(QPalette.WindowText, QColor("#e5e7eb"))
            palette.setColor(QPalette.Base, QColor("#111827"))
            palette.setColor(QPalette.AlternateBase, QColor("#172033"))
            palette.setColor(QPalette.Text, QColor("#e5e7eb"))
            palette.setColor(QPalette.Button, QColor("#1f2937"))
            palette.setColor(QPalette.ButtonText, QColor("#f8fafc"))
            palette.setColor(QPalette.Highlight, QColor("#38bdf8"))
            palette.setColor(QPalette.HighlightedText, QColor("#06111f"))
        else:
            palette.setColor(QPalette.Window, QColor("#f4f7fb"))
            palette.setColor(QPalette.WindowText, QColor("#172033"))
            palette.setColor(QPalette.Base, QColor("#ffffff"))
            palette.setColor(QPalette.AlternateBase, QColor("#eef4fb"))
            palette.setColor(QPalette.Text, QColor("#172033"))
            palette.setColor(QPalette.Button, QColor("#ffffff"))
            palette.setColor(QPalette.ButtonText, QColor("#172033"))
            palette.setColor(QPalette.Highlight, QColor("#2563eb"))
            palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        return palette

    def _theme_stylesheet(self, dark: bool) -> str:
        if dark:
            bg, panel, panel2, text, muted, border, accent, accent2 = (
                "#0f172a", "#111827", "#1f2937", "#e5e7eb", "#94a3b8", "#334155", "#38bdf8", "#0ea5e9"
            )
            input_bg = "#0b1220"
            highlight_text = "#06111f"
        else:
            bg, panel, panel2, text, muted, border, accent, accent2 = (
                "#f4f7fb", "#ffffff", "#eef4fb", "#172033", "#64748b", "#cbd5e1", "#2563eb", "#1d4ed8"
            )
            input_bg = "#ffffff"
            highlight_text = "#ffffff"
        return f"""
        QMainWindow, QDialog {{ background: {bg}; color: {text}; }}
        QMenuBar {{ background: {panel}; color: {text}; padding: 4px; border-bottom: 1px solid {border}; }}
        QMenuBar::item:selected, QMenu {{ background: {panel2}; color: {text}; }}
        QMenu::item:selected {{ background: {accent}; color: #ffffff; }}
        QLabel#AppTitle {{ color: {text}; font-size: 28px; font-weight: 800; letter-spacing: .3px; }}
        QLabel#AppSubtitle {{ color: {muted}; font-size: 13px; }}
        QGroupBox {{ background: {panel}; border: 1px solid {border}; border-radius: 14px; margin-top: 16px; padding: 14px; font-weight: 700; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 8px; color: {accent}; }}
        QPushButton {{ background: {panel2}; color: {text}; border: 1px solid {border}; border-radius: 9px; padding: 8px 12px; font-weight: 600; }}
        QPushButton:hover {{ border-color: {accent}; background: {accent}; color: #ffffff; }}
        QPushButton:pressed {{ background: {accent2}; }}
        QPushButton:disabled {{ color: {muted}; background: {panel}; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QPlainTextEdit, QListWidget {{ background: {input_bg}; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 6px; selection-background-color: {accent}; selection-color: {highlight_text}; }}
        QSpinBox, QDoubleSpinBox {{ min-height: 28px; padding-right: 38px; }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 34px; min-height: 15px; border-left: 1px solid {border}; border-bottom: 1px solid {border}; border-top-right-radius: 8px; background: {panel2}; }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 34px; min-height: 15px; border-left: 1px solid {border}; border-bottom-right-radius: 8px; background: {panel2}; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {accent}; }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: none; width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-bottom: 6px solid {text}; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: none; width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid {text}; }}
        QSpinBox::up-arrow:hover, QSpinBox::down-arrow:hover, QDoubleSpinBox::up-arrow:hover, QDoubleSpinBox::down-arrow:hover {{ border-top-color: {highlight_text}; border-bottom-color: {highlight_text}; }}
        QComboBox {{ padding-right: 28px; }}
        QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 24px; border-left: 1px solid {border}; border-top-right-radius: 8px; border-bottom-right-radius: 8px; background: {panel2}; }}
        QComboBox::down-arrow {{ image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid {text}; margin-right: 7px; }}
        QComboBox QAbstractItemView {{ background: {input_bg}; color: {text}; border: 1px solid {border}; selection-background-color: {accent}; selection-color: {highlight_text}; outline: 0; padding: 4px; }}
        QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 4px 8px; color: {text}; background: {input_bg}; }}
        QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {{ background: {accent}; color: {highlight_text}; }}
        QTableWidget {{ background: {panel}; alternate-background-color: {panel2}; color: {text}; border: 1px solid {border}; border-radius: 12px; gridline-color: {border}; }}
        QHeaderView::section {{ background: {panel2}; color: {muted}; padding: 8px; border: 0; border-bottom: 1px solid {border}; font-weight: 700; }}
        QWidget#PreviewSurface {{ background: {input_bg}; border: 1px solid {border}; border-radius: 12px; color: {muted}; }}
        QCheckBox {{ color: {text}; spacing: 8px; }}
        """

    def _style_table_selection(self) -> None:
        highlight = "#38bdf8" if self._dark_mode else "#2563eb"
        text = "#06111f" if self._dark_mode else "#ffffff"
        pal = self.table.palette()
        pal.setColor(QPalette.Highlight, QColor(highlight))
        pal.setColor(QPalette.HighlightedText, QColor(text))
        self.table.setPalette(pal)
        self.table.setStyleSheet(f"""
        QTableWidget::item {{ border: 0px; padding: 4px 8px; }}
        QTableWidget::item:selected:active, QTableWidget::item:selected:!active {{ background-color: {highlight}; color: {text}; }}
        QTableWidget::item:focus, QTableWidget:focus {{ outline: none; border: 0px; }}
        """)

    def _apply_last_days_range(self, days: int) -> None:
        days = max(1, int(days))
        today = QDate.currentDate()
        start_date = today.addDays(-(days - 1))
        self.filter_from_datetime.setDateTime(QDateTime(start_date, QTime(0, 0, 0)))
        self.filter_to_datetime.setDateTime(QDateTime(today, QTime(23, 59, 59)))

    def _on_last_days_changed(self, value: int) -> None:
        self.filter_from_datetime.blockSignals(True)
        self.filter_to_datetime.blockSignals(True)
        self._apply_last_days_range(value)
        self.filter_from_datetime.blockSignals(False)
        self.filter_to_datetime.blockSignals(False)
        self.refresh()

    def reset_filters(self) -> None:
        widgets = (
            self.prompt_id_input,
            self.filter_category_combo,
            self.filter_variant_combo,
            self.filter_status_combo,
            self.filter_ratio_combo,
            self.filter_checkpoint_base_combo,
            self.filter_last_days_spin,
            self.filter_from_datetime,
            self.filter_to_datetime,
            self.filter_date_order_combo,
        )
        for widget in widgets:
            widget.blockSignals(True)

        self.prompt_id_input.clear()
        self._set_combo_value(self.filter_category_combo, "__ALL__")
        self._set_combo_value(self.filter_variant_combo, "__ALL__")
        self._set_combo_value(self.filter_status_combo, "__ALL__")
        self._set_combo_value(self.filter_ratio_combo, "__ALL__")
        self._set_combo_value(self.filter_checkpoint_base_combo, "__ALL__")
        self.filter_last_days_spin.setValue(30)
        self._apply_last_days_range(self.filter_last_days_spin.value())
        self._set_combo_value(self.filter_date_order_combo, "desc")

        for widget in widgets:
            widget.blockSignals(False)

        self.refresh()

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _refresh_filters(self, *, filters: dict[str, list[str]] | None = None) -> None:
        filters = filters or fetch_prompt_filters()
        self._populate_filter_combo(self.filter_category_combo, "Categoría", filters["categories"])
        self._populate_filter_combo(self.filter_variant_combo, "Versión", filters["variants"])
        self._populate_filter_combo(self.filter_status_combo, "Estado", filters["statuses"])
        self._populate_filter_combo(self.filter_ratio_combo, "Ratio", filters["ratios"])
        self._populate_filter_combo(
            self.filter_checkpoint_base_combo,
            "Checkpoint base",
            filters["checkpoint_bases"],
        )

    def _populate_filter_combo(self, combo: QComboBox, label: str, values: list[str]) -> None:
        current_data = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"Todas ({label})", "__ALL__")
        for value in values:
            combo.addItem(value, value)
        if current_data:
            idx = combo.findData(current_data)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    @staticmethod
    def _format_duration(seconds: int | None) -> str:
        if seconds is None:
            return "—"
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _refresh_status_counts(self, *, counts: dict[str, int] | None = None) -> None:
        counts = counts or fetch_prompt_status_counts()
        self.status_total_label.setText(f"Total: {counts.get('TOTAL', 0)}")
        self.status_created_label.setText(f"CREATED: {counts.get('CREATED', 0)}")
        self.status_queued_label.setText(f"QUEUED: {counts.get('QUEUED', 0)}")
        self.status_sent_label.setText(f"SENT: {counts.get('SENT', 0)}")
        self.status_done_label.setText(f"DONE: {counts.get('DONE', 0)}")
        self.status_failed_label.setText(f"FAILED: {counts.get('FAILED', 0)}")
        self.status_eta_label.setText(f"Tiempo restante: {self._format_duration(counts.get('ETA_SECONDS'))}")

    def _refresh_category_production_counts(
        self,
        *,
        counts: list[tuple[str, int]] | None = None,
    ) -> None:
        counts = counts or self._cached_category_counts or fetch_category_production_counts()
        self.category_production_table.setRowCount(0)
        if not counts:
            self.category_production_table.setRowCount(1)
            self.category_production_table.setItem(0, 0, QTableWidgetItem("Sin datos"))
            self.category_production_table.setItem(0, 1, QTableWidgetItem("—"))
            self.category_production_table.setEnabled(False)
        else:
            self.category_production_table.setEnabled(True)
            self.category_production_table.setRowCount(len(counts))
            for row_index, (category, total) in enumerate(counts):
                self.category_production_table.setItem(
                    row_index,
                    0,
                    QTableWidgetItem(category),
                )
                self.category_production_table.setItem(
                    row_index,
                    1,
                    QTableWidgetItem(str(total)),
                )
        self.category_production_table.resizeColumnsToContents()

    def retry_selected_prompt(self, prompt_id: int | None = None) -> None:
        pid = prompt_id if prompt_id is not None else self._selected_prompt_id()
        if pid is None:
            QMessageBox.warning(self, "Reintentar", "Selecciona un prompt primero.")
            return

        row = self.store.get_prompt_item(pid)

        if not row:
            QMessageBox.warning(self, "Reintentar", f"No existe prompt_item {pid}.")
            return

        status = str(row["status"])
        if status not in {"FAILED", "DONE", "SENT", "QUEUED", "CREATED"}:
            QMessageBox.information(self, "Reintentar", f"Estado actual: {status}")
            return

        confirm = QMessageBox.question(
            self,
            "Reintentar",
            f"¿Reintentar prompt {pid} (estado {status})?",
        )
        if confirm != QMessageBox.Yes:
            return

        existing_job = self.store.get_queue_job_for_prompt(pid, statuses=["PENDING", "RUNNING"])

        if existing_job:
            self.store.reset_queue_job_for_retry(existing_job["id"])
            self.store.set_prompt_item_status(pid, "QUEUED")

            self.refresh()
            QMessageBox.information(
                self,
                "Reintentar",
                f"Prompt {pid} reencolado (job {existing_job['id']}).",
            )
            return

        self.store.set_prompt_item_status(pid, "QUEUED")
        self.store.create_queue_job(prompt_item_id=pid, priority=100)

        self.refresh()
        QMessageBox.information(
            self,
            "Reintentar",
            f"Prompt {pid} reencolado.",
        )

    def delete_selected_prompt(self, prompt_id: int | None = None) -> None:
        pid = prompt_id if prompt_id is not None else self._selected_prompt_id()
        if pid is None:
            QMessageBox.warning(self, "Eliminar", "Selecciona un prompt primero.")
            return

        confirm = QMessageBox.question(
            self,
            "Eliminar",
            f"¿Eliminar prompt {pid}?",
        )
        if confirm != QMessageBox.Yes:
            return

        self.store.delete_prompt_item(pid)

        self.refresh()
        QMessageBox.information(self, "Eliminar", f"Prompt {pid} eliminado.")
