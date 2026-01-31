from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QDateTime, QDate, QTime, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QSpinBox,
    QGroupBox, QComboBox, QAbstractItemView, QPlainTextEdit, QApplication, QDateTimeEdit,
    QLineEdit, QCheckBox, QDialog, QDoubleSpinBox
)

from app.config.app_config import load_app_config
from app.config.waifu_catalog import load_waifu_catalog
from app.data.storage import get_store
from app.services.output_paths import build_output_path
from app.services.pack_service import PackService
from app.services.file_open import open_file, open_folder_and_select
from app.services.checkpoint_service import CheckpointService
from app.services.reel_service import ReelService
from app.domain.models import PackCreate
from app.ui.data_source import (
    fetch_prompts,
    fetch_prompt_filters,
    fetch_prompt_status_counts,
    fetch_category_production_counts,
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
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QProxyStyle, QStyle

class NoFocusRectStyle(QProxyStyle):
    """Elimina el rectángulo de foco (focus rect) que en Windows 11 aparece como marcas/lineas."""
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_FrameFocusRect:
            return
        super().drawPrimitive(element, option, painter, widget)

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Waifu Desktop — Cola & Resultados")
        self.resize(1200, 750)
        self.setStyleSheet("""
        QGroupBox {
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }
        """)
        self._base_path: Path | None = None

        self.store = get_store()
        self.pack_service = PackService()
        self.reel_service = ReelService()
        self.waifu_catalog = load_waifu_catalog()
        self.app_config = load_app_config()
        self.prompt_base_window: PromptBaseWindow | None = None
        self.prompt_variation_window: PromptVariationWindow | None = None
        self.social_copy_window: SocialCopyWindow | None = None

        # Mantener pixmaps originales para reescalar en resizeEvent
        self._pix_base: QPixmap | None = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._run_scheduled_refresh)
        self._refresh_resize_columns = False
        self._refresh_worker: RefreshWorker | None = None
        self._refresh_pending = False
        self._cached_filters: dict[str, list[str]] | None = None
        self._cached_status_counts: dict[str, int] | None = None
        self._cached_category_counts: list[tuple[str, int]] | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        menu = self.menuBar()
        file_menu = menu.addMenu("Archivo")
        queue_menu = menu.addMenu("Cola")
        view_menu = menu.addMenu("Vista")
        maintenance_menu = menu.addMenu("Mantenimiento")
        self.open_base_action = file_menu.addAction("Abrir Base")
        self.open_up_action = file_menu.addAction("Abrir Upscale")
        self.open_folder_base_action = file_menu.addAction("Abrir Carpeta (Base)")
        self.open_folder_up_action = file_menu.addAction("Abrir Carpeta (Upscale)")
        file_menu.addSeparator()
        self.exit_action = file_menu.addAction("Salir")
        self.exit_action.triggered.connect(self.close)

        self.refresh_action = queue_menu.addAction("Refrescar")
        self.pause_action = queue_menu.addAction("Pausar cola")
        self.resume_action = queue_menu.addAction("Reanudar cola")
        self.refresh_action.setShortcut("F5")
        self.pause_action.setShortcut("Ctrl+Shift+P")
        self.resume_action.setShortcut("Ctrl+Shift+R")

        self.toggle_preview_action = view_menu.addAction("Mostrar preview")
        self.toggle_preview_action.setCheckable(True)
        self.toggle_preview_action.setChecked(False)
        self.toggle_worker_log_action = view_menu.addAction("Mostrar log del worker")
        self.toggle_worker_log_action.setCheckable(True)
        self.toggle_worker_log_action.setChecked(True)
        self.view_production_action = view_menu.addAction("Ver producción")
        self.view_production_action.triggered.connect(self.open_production_dialog)

        self.open_prompt_base_action = maintenance_menu.addAction("Categorías y personajes")
        self.open_prompt_base_action.triggered.connect(self.open_prompt_base_window)
        self.open_prompt_variation_action = maintenance_menu.addAction("Opciones y variaciones")
        self.open_prompt_variation_action.triggered.connect(self.open_prompt_variation_window)
        self.open_social_copy_action = maintenance_menu.addAction("Copys redes sociales")
        self.open_social_copy_action.triggered.connect(self.open_social_copy_window)

        header = QHBoxLayout()
        title_stack = QVBoxLayout()
        title_label = QLabel("Waifu Desktop")
        title_label.setStyleSheet("font-size: 22px; font-weight: 700;")
        subtitle_label = QLabel("Panel comercial de producción, cola y resultados")
        subtitle_label.setStyleSheet("color: #9aa0a6; font-size: 12px;")
        title_stack.addWidget(title_label)
        title_stack.addWidget(subtitle_label)
        header.addLayout(title_stack)
        header.addStretch(1)
        layout.addLayout(header)

        quick_actions = QHBoxLayout()
        quick_actions.setSpacing(10)
        self.open_filters_btn = QPushButton("Filtros inteligentes")
        self.open_pack_btn = QPushButton("Generar pack")
        self.open_reel_btn = QPushButton("Reel Instagram")
        quick_actions.addWidget(self.open_filters_btn)
        quick_actions.addWidget(self.open_pack_btn)
        quick_actions.addWidget(self.open_reel_btn)
        quick_actions.addStretch(1)
        layout.addLayout(quick_actions)

        summary_group = QGroupBox("Resumen rápido")
        summary_layout = QHBoxLayout(summary_group)
        self.status_total_label = QLabel("Total: 0")
        self.status_created_label = QLabel("CREATED: 0")
        self.status_queued_label = QLabel("QUEUED: 0")
        self.status_sent_label = QLabel("SENT: 0")
        self.status_done_label = QLabel("DONE: 0")
        self.status_failed_label = QLabel("FAILED: 0")
        summary_layout.addStretch(1)
        for lbl in (
            self.status_total_label,
            self.status_created_label,
            self.status_queued_label,
            self.status_sent_label,
            self.status_done_label,
            self.status_failed_label,
        ):
            summary_layout.addWidget(lbl)
        summary_layout.addStretch(1)
        layout.addWidget(summary_group)

        operation_group = QGroupBox("Operación")
        operation_layout = QGridLayout(operation_group)
        self.start_worker_btn = QPushButton("Iniciar Worker")
        self.stop_worker_btn = QPushButton("Parar Worker")
        self.stop_worker_btn.setEnabled(False)

        self.worker_status_label = QLabel("Worker: STOPPED")
        self.worker_status_label.setAlignment(Qt.AlignVCenter)

        operation_layout.addWidget(self.start_worker_btn, 0, 0)
        operation_layout.addWidget(self.stop_worker_btn, 0, 1)
        operation_layout.addWidget(self.worker_status_label, 0, 2, 1, 3)

        operation_layout.addWidget(QLabel("Mostrar:"), 1, 0)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 500)
        self.limit_spin.setValue(200)
        operation_layout.addWidget(self.limit_spin, 1, 1)

        operation_layout.addWidget(QLabel("Pausa (s):"), 1, 2)
        self.pause_between_spin = QSpinBox()
        self.pause_between_spin.setRange(0, 60)
        self.pause_between_spin.setValue(5)
        self.pause_between_spin.setToolTip("Segundos de descanso entre imágenes procesadas.")
        operation_layout.addWidget(self.pause_between_spin, 1, 3)

        self.preview_toggle_check = QCheckBox("Mostrar preview")
        self.preview_toggle_check.setChecked(False)
        operation_layout.addWidget(self.preview_toggle_check, 2, 0, 1, 2)
        operation_layout.setColumnStretch(4, 1)
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

        self.pack_generate_btn = QPushButton("Generar Pack")
        pack_layout.addWidget(self.pack_generate_btn, 1, 6, 1, 2)
        pack_layout.setColumnStretch(8, 1)

        pack_layout.addWidget(QLabel("Característica extra:"), 2, 0)
        self.pack_manual_feature_input = QLineEdit()
        self.pack_manual_feature_input.setPlaceholderText("Añade una característica común para todo el pack")
        pack_layout.addWidget(self.pack_manual_feature_input, 2, 1, 1, 7)

        pack_dialog_layout.addWidget(pack_group)

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

        self.reel_generate_btn = QPushButton("Crear Reel")
        reel_layout.addWidget(self.reel_generate_btn, 0, 8)
        reel_layout.setColumnStretch(9, 1)

        reel_dialog_layout.addWidget(reel_group)

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
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Categoría",
            "Base",
            "Upscale",
            "Reel",
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

        # 1) Quita las marcas de foco en Windows 11
        self.table.setStyle(NoFocusRectStyle(self.table.style()))

        # 2) Fuerza colores de selección (fondo + texto) a nivel de palette
        pal = self.table.palette()
        pal.setColor(QPalette.Highlight, QColor("#2b2f36"))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.table.setPalette(pal)

        # 3) Refuerza en QSS (incluye estados active/inactive para que SIEMPRE se vea el texto)
        self.table.setStyleSheet("""
        QTableWidget::item {
        border: 0px;
        padding: 2px 6px;
        }
        QTableWidget::item:selected:active {
        background-color: #2b2f36;
        color: #ffffff;
        }
        QTableWidget::item:selected:!active {
        background-color: #2b2f36;
        color: #ffffff;
        }
        QTableWidget::item:focus {
        outline: none;
        border: 0px;
        }
        QTableWidget:focus {
        outline: none;
        }
        QHeaderView::section {
        padding: 6px;
        border: 0px;
        }
        """)

        left_column.addWidget(self.table, 1)

        # Base preview group (right column)
        self.base_group = QGroupBox("Preview Base")
        base_layout = QVBoxLayout(self.base_group)
        self.base_image_label = ClickableLabel("(sin base)")
        self.base_image_label.setAlignment(Qt.AlignCenter)
        self.base_image_label.setMinimumHeight(240)
        self.base_image_label.setStyleSheet("border: 1px solid #444;")
        base_layout.addWidget(self.base_image_label)

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

        self.open_base_action.triggered.connect(lambda: self.open_selected("base"))
        self.open_up_action.triggered.connect(lambda: self.open_selected("upscale"))
        self.open_folder_base_action.triggered.connect(lambda: self.open_selected("folder_base"))
        self.open_folder_up_action.triggered.connect(lambda: self.open_selected("folder_upscale"))
        # Selection changes => enable/disable + preview update
        self.table.itemSelectionChanged.connect(self._sync_current_cell_to_selection)
        self.table.itemSelectionChanged.connect(self.update_actions_state)
        self.table.itemDoubleClicked.connect(self.open_prompt_dialog_from_item)

        # Estado inicial botones (deshabilitados hasta tener selección válida)
        self.open_base_action.setEnabled(False)
        self.open_up_action.setEnabled(False)
        self.open_folder_base_action.setEnabled(False)
        self.open_folder_up_action.setEnabled(False)
        self.worker_thread: WorkerThread | None = None

        self.start_worker_btn.clicked.connect(self.start_worker)
        self.stop_worker_btn.clicked.connect(self.stop_worker)
        self.pack_generate_btn.clicked.connect(self.generate_pack)
        self.reel_generate_btn.clicked.connect(self.generate_reel)
        self.open_filters_btn.clicked.connect(self.filters_dialog.show)
        self.open_pack_btn.clicked.connect(self.pack_dialog.show)
        self.open_reel_btn.clicked.connect(self.reel_dialog.show)
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
        self.reset_filters_btn.clicked.connect(self.reset_filters)
        self.toggle_preview_action.toggled.connect(self._toggle_base_preview)
        self.preview_toggle_check.toggled.connect(self._toggle_base_preview)
        self.toggle_worker_log_action.toggled.connect(self._toggle_worker_log)
        self.clear_worker_log_btn.clicked.connect(self.clear_worker_log)
        self.pack_combination_combo.currentIndexChanged.connect(self._update_nsfw_controls)
        self._populate_pack_selectors()
        self._populate_checkpoint_selectors()
        self._update_nsfw_controls()

        self._update_right_column_visibility()
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
        self._start_refresh(resize_columns=True)

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
        )
        worker.result.connect(self._on_refresh_result)
        worker.failed.connect(self._on_refresh_failed)
        worker.finished.connect(self._clear_refresh_worker)
        self._refresh_worker = worker
        worker.start()

    def _clear_refresh_worker(self) -> None:
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
            self.table.setItem(i, 5, QTableWidgetItem(row.variant))
            self.table.setItem(i, 6, QTableWidgetItem(row.status))
            self.table.setItem(i, 7, QTableWidgetItem(row.datestamp))
            self.table.setItem(i, 8, QTableWidgetItem(row.title))
            self.table.setItem(i, 9, QTableWidgetItem(row.ratio))
            self.table.setItem(i, 10, QTableWidgetItem(row.checkpoint_base or "—"))
            self.table.setItem(i, 11, QTableWidgetItem(row.checkpoint_refiner or "—"))

        if payload.resize_columns:
            self.table.resizeColumnsToContents()

        # Recalcular botones + preview tras refrescar
        self.update_actions_state()

        self._cached_filters = payload.filters
        self._cached_status_counts = payload.status_counts
        self._cached_category_counts = payload.category_counts
        self._refresh_filters(filters=payload.filters)
        self._refresh_status_counts(counts=payload.status_counts)
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

    def on_prompt_base_updated(self) -> None:
        self._reload_waifu_catalog()
        self._populate_pack_selectors()

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

    def _update_nsfw_controls(self) -> None:
        combination_key = self.pack_combination_combo.currentData()
        is_nsfw = combination_key == "nsfw"
        self.pack_nsfw_tag_label.setVisible(is_nsfw)
        self.pack_nsfw_tag_spin.setVisible(is_nsfw)

    def _populate_checkpoint_selectors(self) -> None:
        service = CheckpointService()
        models = service.list_available()
        default_base, default_refiner = service.get_default_checkpoints()

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

    def generate_reel(self) -> None:
        category = self.reel_category_combo.currentData()
        quantity = int(self.reel_quantity_spin.value())
        seconds_per_image = float(self.reel_seconds_spin.value())
        variant = self.reel_variant_combo.currentData()
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
            )
        except Exception as exc:
            QMessageBox.critical(self, "Reel Instagram", str(exc))
            return

        try:
            open_folder_and_select(result.folder)
        except Exception as exc:
            QMessageBox.critical(self, "Reel Instagram", f"No se pudo abrir la carpeta: {exc}")

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

    def _set_preview(self, *, which: str, path: Path | None) -> None:
        if which != "base":
            return

        self._base_path = path
        img_label = self.base_image_label
        self._pix_base = None

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

    def _rescale_previews(self) -> None:
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

    # -------- Selection: enable actions + update preview --------

    def update_actions_state(self) -> None:
        pid = self._selected_prompt_id()
        if pid is None:
            self.open_base_action.setEnabled(False)
            self.open_up_action.setEnabled(False)
            self.open_folder_base_action.setEnabled(False)
            self.open_folder_up_action.setEnabled(False)
            self._set_preview(which="base", path=None)
            return

        r = self.store.get_prompt_item_media(pid)
        has_base = bool(r and r.get("base_image_json"))
        has_up = bool(r and r.get("upscale_image_json"))

        self.open_base_action.setEnabled(has_base)
        self.open_folder_base_action.setEnabled(has_base)
        self.open_up_action.setEnabled(has_up)
        self.open_folder_up_action.setEnabled(has_up)

        base_path: Path | None = None
        if r and r.get("base_image_json"):
            base = json.loads(r["base_image_json"])
            base_path = build_output_path(base)

        self._set_preview(which="base", path=base_path)

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

        try:
            if mode == "base":
                if not base:
                    raise RuntimeError("Este item no tiene base_image_json.")
                open_file(build_output_path(base))

            elif mode == "upscale":
                if not up:
                    raise RuntimeError("Este item no tiene upscale_image_json.")
                open_file(build_output_path(up))

            elif mode == "folder_base":
                if not base:
                    raise RuntimeError("Este item no tiene base_image_json.")
                open_folder_and_select(build_output_path(base))

            elif mode == "folder_upscale":
                if not up:
                    raise RuntimeError("Este item no tiene upscale_image_json.")
                open_folder_and_select(build_output_path(up))

            else:
                raise RuntimeError("Modo desconocido.")

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def closeEvent(self, event) -> None:
        try:
            if self._refresh_timer.isActive():
                self._refresh_timer.stop()
            if self._refresh_worker and self._refresh_worker.isRunning():
                self._refresh_worker.wait(2000)
                if self._refresh_worker.isRunning():
                    self._refresh_worker.terminate()
                    self._refresh_worker.wait(1000)
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.stop()
                self.worker_thread.wait(2000)
                if self.worker_thread.isRunning():
                    self.worker_thread.terminate()
                    self.worker_thread.wait(1000)
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

    def _refresh_status_counts(self, *, counts: dict[str, int] | None = None) -> None:
        counts = counts or fetch_prompt_status_counts()
        self.status_total_label.setText(f"Total: {counts.get('TOTAL', 0)}")
        self.status_created_label.setText(f"CREATED: {counts.get('CREATED', 0)}")
        self.status_queued_label.setText(f"QUEUED: {counts.get('QUEUED', 0)}")
        self.status_sent_label.setText(f"SENT: {counts.get('SENT', 0)}")
        self.status_done_label.setText(f"DONE: {counts.get('DONE', 0)}")
        self.status_failed_label.setText(f"FAILED: {counts.get('FAILED', 0)}")

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
