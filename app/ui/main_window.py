from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QSpinBox,
    QGroupBox, QComboBox, QAbstractItemView, QPlainTextEdit, QApplication
)

from app.config.app_config import load_app_config
from app.config.waifu_catalog import load_waifu_catalog
from app.data.db import get_connection
from app.data.kv_store import KVStore
from app.services.output_paths import build_output_path
from app.services.pack_service import PackService
from app.services.file_open import open_file, open_folder_and_select
from app.domain.models import PackCreate
from app.ui.data_source import fetch_prompts, fetch_prompt_filters, fetch_prompt_status_counts
from app.ui.worker_thread import WorkerThread
from app.ui.clickable_label import ClickableLabel
from app.ui.image_viewer import ImageViewer
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
        self._base_path: Path | None = None

        self.kv = KVStore()
        self.pack_service = PackService()
        self.waifu_catalog = load_waifu_catalog()
        self.app_config = load_app_config()

        # Mantener pixmaps originales para reescalar en resizeEvent
        self._pix_base: QPixmap | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # Top bar
        top = QHBoxLayout()
        layout.addLayout(top)

        self.refresh_btn = QPushButton("Refrescar")
        self.pause_btn = QPushButton("Pausar cola")
        self.resume_btn = QPushButton("Reanudar cola")

        self.start_worker_btn = QPushButton("Iniciar Worker")
        self.stop_worker_btn = QPushButton("Parar Worker")
        self.stop_worker_btn.setEnabled(False)

        self.worker_status_label = QLabel("Worker: STOPPED")
        self.worker_status_label.setAlignment(Qt.AlignVCenter)

        top.addWidget(self.start_worker_btn)
        top.addWidget(self.stop_worker_btn)
        top.addWidget(self.worker_status_label)

        top.addWidget(self.refresh_btn)
        top.addWidget(self.pause_btn)
        top.addWidget(self.resume_btn)

        top.addWidget(QLabel("Mostrar:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 500)
        self.limit_spin.setValue(50)
        top.addWidget(self.limit_spin)

        top.addWidget(QLabel("Categoría:"))
        self.filter_category_combo = QComboBox()
        self.filter_category_combo.setMinimumWidth(130)
        top.addWidget(self.filter_category_combo)

        top.addWidget(QLabel("Versión:"))
        self.filter_variant_combo = QComboBox()
        self.filter_variant_combo.setMinimumWidth(130)
        top.addWidget(self.filter_variant_combo)

        top.addWidget(QLabel("Estado:"))
        self.filter_status_combo = QComboBox()
        self.filter_status_combo.setMinimumWidth(130)
        top.addWidget(self.filter_status_combo)

        top.addWidget(QLabel("Ratio:"))
        self.filter_ratio_combo = QComboBox()
        self.filter_ratio_combo.setMinimumWidth(110)
        top.addWidget(self.filter_ratio_combo)

        top.addStretch(1)

        # Pack generator
        pack_group = QGroupBox("Generar Pack")
        pack_layout = QHBoxLayout(pack_group)

        pack_layout.addWidget(QLabel("Categoría:"))
        self.pack_category_combo = QComboBox()
        pack_layout.addWidget(self.pack_category_combo)

        pack_layout.addWidget(QLabel("Variante:"))
        self.pack_variant_combo = QComboBox()
        pack_layout.addWidget(self.pack_variant_combo)

        pack_layout.addWidget(QLabel("Cantidad:"))
        self.pack_quantity_spin = QSpinBox()
        self.pack_quantity_spin.setRange(1, 500)
        self.pack_quantity_spin.setValue(10)
        pack_layout.addWidget(self.pack_quantity_spin)

        self.pack_generate_btn = QPushButton("Generar Pack")
        pack_layout.addWidget(self.pack_generate_btn)
        pack_layout.addStretch(1)

        layout.addWidget(pack_group)

        main_content = QHBoxLayout()
        layout.addLayout(main_content, 1)

        left_column = QVBoxLayout()
        main_content.addLayout(left_column, 7)

        # Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Categoría", "Versión", "Estado", "Título", "Ratio", "Base", "Upscale"
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

        # Prompt preview
        self.prompt_group = QGroupBox("Prompt")
        prompt_layout = QVBoxLayout(self.prompt_group)
        self.prompt_preview_text = QPlainTextEdit("—")
        self.prompt_preview_text.setReadOnly(True)
        self.prompt_preview_text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.prompt_preview_text.setStyleSheet("font-weight: 600;")
        prompt_layout.addWidget(self.prompt_preview_text)

        prompt_actions = QHBoxLayout()
        self.copy_prompt_btn = QPushButton("Copiar prompt")
        self.retry_prompt_btn = QPushButton("Reintentar prompt")
        self.delete_prompt_btn = QPushButton("Eliminar prompt")
        prompt_actions.addStretch(1)
        prompt_actions.addWidget(self.copy_prompt_btn)
        prompt_actions.addWidget(self.retry_prompt_btn)
        prompt_actions.addWidget(self.delete_prompt_btn)
        prompt_layout.addLayout(prompt_actions)

        left_column.addWidget(self.prompt_group, 0)

        # Base preview group (right column)
        self.base_group = QGroupBox("Preview Base")
        base_layout = QVBoxLayout(self.base_group)
        self.base_image_label = ClickableLabel("(sin base)")
        self.base_image_label.setAlignment(Qt.AlignCenter)
        self.base_image_label.setMinimumHeight(240)
        self.base_image_label.setStyleSheet("border: 1px solid #444;")
        base_layout.addWidget(self.base_image_label)

        self.base_image_label.doubleClicked.connect(lambda: self.open_preview_dialog("base"))

        main_content.addWidget(self.base_group, 3)

        # Bottom actions
        bottom = QHBoxLayout()
        layout.addLayout(bottom)

        self.open_base_btn = QPushButton("Abrir Base")
        self.open_up_btn = QPushButton("Abrir Upscale")
        self.open_folder_base_btn = QPushButton("Abrir Carpeta (Base)")
        self.open_folder_up_btn = QPushButton("Abrir Carpeta (Upscale)")

        bottom.addWidget(self.open_base_btn)
        bottom.addWidget(self.open_up_btn)
        bottom.addWidget(self.open_folder_base_btn)
        bottom.addWidget(self.open_folder_up_btn)
        bottom.addStretch(1)

        # Status counters
        status_row = QHBoxLayout()
        self.status_total_label = QLabel("Total: 0")
        self.status_created_label = QLabel("CREATED: 0")
        self.status_queued_label = QLabel("QUEUED: 0")
        self.status_sent_label = QLabel("SENT: 0")
        self.status_done_label = QLabel("DONE: 0")
        self.status_failed_label = QLabel("FAILED: 0")
        status_row.addStretch(1)
        for lbl in (
            self.status_total_label,
            self.status_created_label,
            self.status_queued_label,
            self.status_sent_label,
            self.status_done_label,
            self.status_failed_label,
        ):
            status_row.addWidget(lbl)
        status_row.addStretch(1)
        layout.addLayout(status_row)

        # Signals
        self.refresh_btn.clicked.connect(self.refresh)
        self.pause_btn.clicked.connect(self.pause_queue)
        self.resume_btn.clicked.connect(self.resume_queue)

        self.open_base_btn.clicked.connect(lambda: self.open_selected("base"))
        self.open_up_btn.clicked.connect(lambda: self.open_selected("upscale"))
        self.open_folder_base_btn.clicked.connect(lambda: self.open_selected("folder_base"))
        self.open_folder_up_btn.clicked.connect(lambda: self.open_selected("folder_upscale"))
        self.copy_prompt_btn.clicked.connect(self.copy_prompt_to_clipboard)

        # Selection changes => enable/disable + preview update
        self.table.itemSelectionChanged.connect(self._sync_current_cell_to_selection)
        self.table.itemSelectionChanged.connect(self.update_actions_state)

        # Estado inicial botones (deshabilitados hasta tener selección válida)
        self.open_base_btn.setEnabled(False)
        self.open_up_btn.setEnabled(False)
        self.open_folder_base_btn.setEnabled(False)
        self.open_folder_up_btn.setEnabled(False)
        self.retry_prompt_btn.setEnabled(False)
        self.delete_prompt_btn.setEnabled(False)

        self.worker_thread: WorkerThread | None = None

        self.start_worker_btn.clicked.connect(self.start_worker)
        self.stop_worker_btn.clicked.connect(self.stop_worker)
        self.pack_generate_btn.clicked.connect(self.generate_pack)
        self.retry_prompt_btn.clicked.connect(self.retry_selected_prompt)
        self.delete_prompt_btn.clicked.connect(self.delete_selected_prompt)
        self.limit_spin.valueChanged.connect(self.refresh)
        self.filter_category_combo.currentIndexChanged.connect(self.refresh)
        self.filter_variant_combo.currentIndexChanged.connect(self.refresh)
        self.filter_status_combo.currentIndexChanged.connect(self.refresh)
        self.filter_ratio_combo.currentIndexChanged.connect(self.refresh)

        self._populate_pack_selectors()

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
        with get_connection() as conn:
            with conn:
                self.kv.set(conn, "queue_paused", "true")

        self.refresh()
        QMessageBox.information(self, "Cola", "Cola pausada.")

    def resume_queue(self) -> None:
        with get_connection() as conn:
            with conn:
                self.kv.set(conn, "queue_paused", "false")
        self.refresh()
        QMessageBox.information(self, "Cola", "Cola reanudada.")

    # -------- Table / Data --------

    def refresh(self) -> None:
        limit = int(self.limit_spin.value())
        category = self._selected_filter_value(self.filter_category_combo)
        variant = self._selected_filter_value(self.filter_variant_combo)
        status = self._selected_filter_value(self.filter_status_combo)
        ratio = self._selected_filter_value(self.filter_ratio_combo)

        data = fetch_prompts(
            limit=limit,
            category=category,
            variant=variant,
            status=status,
            ratio=ratio,
        )

        self.table.setRowCount(len(data))
        for i, row in enumerate(data):
            self.table.setItem(i, 0, QTableWidgetItem(str(row.id)))
            self.table.setItem(i, 1, QTableWidgetItem(row.category))
            self.table.setItem(i, 2, QTableWidgetItem(row.variant))
            self.table.setItem(i, 3, QTableWidgetItem(row.status))
            self.table.setItem(i, 4, QTableWidgetItem(row.title))
            self.table.setItem(i, 5, QTableWidgetItem(row.ratio))
            self.table.setItem(i, 6, QTableWidgetItem("✅" if row.has_base else "—"))
            self.table.setItem(i, 7, QTableWidgetItem("✅" if row.has_upscale else "—"))

        self.table.resizeColumnsToContents()

        # Recalcular botones + preview tras refrescar
        self.update_actions_state()

        self._refresh_filters()
        self._refresh_status_counts()

        with get_connection() as conn:
            paused = self.kv.get(conn, "queue_paused", "false")

        is_paused = paused == "true"
        self.pause_btn.setEnabled(not is_paused)
        self.resume_btn.setEnabled(is_paused)

    def _selected_prompt_id(self) -> int | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        pid_item = self.table.item(row, 0)
        if not pid_item:
            return None
        return int(pid_item.text())

    def _populate_pack_selectors(self) -> None:
        self.pack_category_combo.clear()
        for key, data in self.waifu_catalog.categories.items():
            if not data.get("enabled", True):
                continue
            label = str(data.get("label", key))
            self.pack_category_combo.addItem(label, key)

        self.pack_variant_combo.clear()
        for key in self.app_config.variants.keys():
            self.pack_variant_combo.addItem(key, key)

        if self.pack_category_combo.count() == 0:
            self.pack_generate_btn.setEnabled(False)

    def generate_pack(self) -> None:
        category = self.pack_category_combo.currentData()
        variant = self.pack_variant_combo.currentData()
        quantity = int(self.pack_quantity_spin.value())

        if not category or not variant:
            QMessageBox.warning(self, "Generar Pack", "Selecciona categoría y variante.")
            return

        req = PackCreate(
            category=str(category),
            variant=str(variant),
            requested_n=quantity,
        )

        try:
            with get_connection() as conn:
                with conn:
                    result = self.pack_service.create_pack_and_enqueue(conn, req)
        except Exception as exc:
            QMessageBox.critical(self, "Generar Pack", str(exc))
            return

        self.refresh()
        QMessageBox.information(
            self,
            "Generar Pack",
            f"Pack {result.pack_id} creado con {len(result.created_prompt_item_ids)} items.",
        )

    # -------- Preview helpers --------

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
            self.open_base_btn.setEnabled(False)
            self.open_up_btn.setEnabled(False)
            self.open_folder_base_btn.setEnabled(False)
            self.open_folder_up_btn.setEnabled(False)
            self.retry_prompt_btn.setEnabled(False)
            self.delete_prompt_btn.setEnabled(False)
            self.prompt_preview_text.setPlainText("—")
            self._set_preview(which="base", path=None)
            return

        with get_connection() as conn:
            r = conn.execute(
                "SELECT prompt_text, base_image_json, upscale_image_json FROM prompt_item WHERE id=?",
                (pid,),
            ).fetchone()

        has_base = bool(r and r["base_image_json"])
        has_up = bool(r and r["upscale_image_json"])

        self.prompt_preview_text.setPlainText(str(r["prompt_text"]) if r else "—")

        self.open_base_btn.setEnabled(has_base)
        self.open_folder_base_btn.setEnabled(has_base)
        self.open_up_btn.setEnabled(has_up)
        self.open_folder_up_btn.setEnabled(has_up)
        self.retry_prompt_btn.setEnabled(True)
        self.delete_prompt_btn.setEnabled(True)

        base_path: Path | None = None
        if r and r["base_image_json"]:
            base = json.loads(r["base_image_json"])
            base_path = build_output_path(base)

        self._set_preview(which="base", path=base_path)

    # -------- Open actions --------

    def start_worker(self) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            return

        self.worker_thread = WorkerThread(poll_idle_seconds=1.0)
        self.worker_thread.status.connect(self.on_worker_status)
        self.worker_thread.processed.connect(self.on_worker_processed)
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

    def on_worker_processed(self) -> None:
        self.refresh()

    def open_selected(self, mode: str) -> None:
        pid = self._selected_prompt_id()
        if pid is None:
            QMessageBox.warning(self, "Abrir", "Selecciona una fila primero.")
            return

        with get_connection() as conn:
            r = conn.execute(
                "SELECT base_image_json, upscale_image_json FROM prompt_item WHERE id=?",
                (pid,),
            ).fetchone()

        if not r:
            QMessageBox.warning(self, "Abrir", f"No existe prompt_item {pid}.")
            return

        base = json.loads(r["base_image_json"]) if r["base_image_json"] else None
        up = json.loads(r["upscale_image_json"]) if r["upscale_image_json"] else None

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
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.stop()
                self.worker_thread.wait(2000)
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

    def copy_prompt_to_clipboard(self) -> None:
        prompt = self.prompt_preview_text.toPlainText().strip()
        if not prompt or prompt == "—":
            return
        QApplication.clipboard().setText(prompt)

    def _selected_filter_value(self, combo: QComboBox) -> str | None:
        value = combo.currentData()
        if value is None or value == "__ALL__":
            return None
        return str(value)

    def _refresh_filters(self) -> None:
        filters = fetch_prompt_filters()
        self._populate_filter_combo(self.filter_category_combo, "Categoría", filters["categories"])
        self._populate_filter_combo(self.filter_variant_combo, "Versión", filters["variants"])
        self._populate_filter_combo(self.filter_status_combo, "Estado", filters["statuses"])
        self._populate_filter_combo(self.filter_ratio_combo, "Ratio", filters["ratios"])

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

    def _refresh_status_counts(self) -> None:
        counts = fetch_prompt_status_counts()
        self.status_total_label.setText(f"Total: {counts.get('TOTAL', 0)}")
        self.status_created_label.setText(f"CREATED: {counts.get('CREATED', 0)}")
        self.status_queued_label.setText(f"QUEUED: {counts.get('QUEUED', 0)}")
        self.status_sent_label.setText(f"SENT: {counts.get('SENT', 0)}")
        self.status_done_label.setText(f"DONE: {counts.get('DONE', 0)}")
        self.status_failed_label.setText(f"FAILED: {counts.get('FAILED', 0)}")

    def retry_selected_prompt(self) -> None:
        pid = self._selected_prompt_id()
        if pid is None:
            QMessageBox.warning(self, "Reintentar", "Selecciona un prompt primero.")
            return

        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, status, pack_id, title, prompt_text, negative_text, meta_json, combo_key, signature
                FROM prompt_item
                WHERE id=?
                """,
                (pid,),
            ).fetchone()

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

        with get_connection() as conn:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO prompt_item (
                        pack_id,
                        title,
                        prompt_text,
                        negative_text,
                        meta_json,
                        combo_key,
                        signature,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'QUEUED')
                    """,
                    (
                        row["pack_id"],
                        row["title"],
                        row["prompt_text"],
                        row["negative_text"],
                        row["meta_json"],
                        row["combo_key"],
                        row["signature"],
                    ),
                )
                new_prompt_id = int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO queue_job(prompt_item_id, priority, status)
                    VALUES (?, 100, 'PENDING')
                    """,
                    (new_prompt_id,),
                )

        self.refresh()
        QMessageBox.information(
            self,
            "Reintentar",
            f"Prompt {pid} reencolado como {new_prompt_id}.",
        )

    def delete_selected_prompt(self) -> None:
        pid = self._selected_prompt_id()
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

        with get_connection() as conn:
            with conn:
                conn.execute("DELETE FROM prompt_item WHERE id=?", (pid,))

        self.refresh()
        QMessageBox.information(self, "Eliminar", f"Prompt {pid} eliminado.")
