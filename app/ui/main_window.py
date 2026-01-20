from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QSpinBox,
    QGroupBox, QComboBox
)

from app.config.app_config import load_app_config
from app.config.waifu_catalog import load_waifu_catalog
from app.data.db import get_connection
from app.data.kv_store import KVStore
from app.services.output_paths import build_output_path
from app.services.pack_service import PackService
from app.services.file_open import open_file, open_folder_and_select
from app.domain.models import PackCreate
from app.ui.data_source import fetch_latest_prompts
from app.ui.worker_thread import WorkerThread
from app.ui.clickable_label import ClickableLabel
from app.ui.image_viewer import ImageViewer




class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Waifu Desktop — Cola & Resultados")
        self.resize(1200, 750)
        self._base_path: Path | None = None
        self._up_path: Path | None = None


        self.kv = KVStore()
        self.pack_service = PackService()
        self.waifu_catalog = load_waifu_catalog()
        self.app_config = load_app_config()

        # Mantener pixmaps originales para reescalar en resizeEvent
        self._pix_base: QPixmap | None = None
        self._pix_up: QPixmap | None = None

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

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Categoría", "Versión", "Estado", "Título", "Base", "Upscale"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        # Preview panel (Base | Upscale)
        preview_row = QHBoxLayout()
        layout.addLayout(preview_row)

        # Base preview group
        self.base_group = QGroupBox("Preview Base")
        base_layout = QVBoxLayout(self.base_group)
        self.base_path_label = QLabel("—")
        self.base_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.base_image_label = ClickableLabel("(sin base)")
        self.base_image_label.setAlignment(Qt.AlignCenter)
        self.base_image_label.setMinimumHeight(240)
        self.base_image_label.setStyleSheet("border: 1px solid #444;")
        base_layout.addWidget(self.base_path_label)
        base_layout.addWidget(self.base_image_label)

        # Upscale preview group
        self.up_group = QGroupBox("Preview Upscale")
        up_layout = QVBoxLayout(self.up_group)
        self.up_path_label = QLabel("—")
        self.up_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.up_image_label = ClickableLabel("(sin upscale)")
        self.up_image_label.setAlignment(Qt.AlignCenter)
        self.up_image_label.setMinimumHeight(240)
        self.up_image_label.setStyleSheet("border: 1px solid #444;")
        up_layout.addWidget(self.up_path_label)
        up_layout.addWidget(self.up_image_label)

        self.base_image_label.doubleClicked.connect(lambda: self.open_preview_dialog("base"))
        self.up_image_label.doubleClicked.connect(lambda: self.open_preview_dialog("upscale"))


        preview_row.addWidget(self.base_group, 1)
        preview_row.addWidget(self.up_group, 1)

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

        # Signals
        self.refresh_btn.clicked.connect(self.refresh)
        self.pause_btn.clicked.connect(self.pause_queue)
        self.resume_btn.clicked.connect(self.resume_queue)

        self.open_base_btn.clicked.connect(lambda: self.open_selected("base"))
        self.open_up_btn.clicked.connect(lambda: self.open_selected("upscale"))
        self.open_folder_base_btn.clicked.connect(lambda: self.open_selected("folder_base"))
        self.open_folder_up_btn.clicked.connect(lambda: self.open_selected("folder_upscale"))

        # Selection changes => enable/disable + preview update
        self.table.itemSelectionChanged.connect(self.update_actions_state)

        # Estado inicial botones (deshabilitados hasta tener selección válida)
        self.open_base_btn.setEnabled(False)
        self.open_up_btn.setEnabled(False)
        self.open_folder_base_btn.setEnabled(False)
        self.open_folder_up_btn.setEnabled(False)

        self.worker_thread: WorkerThread | None = None

        self.start_worker_btn.clicked.connect(self.start_worker)
        self.stop_worker_btn.clicked.connect(self.stop_worker)
        self.pack_generate_btn.clicked.connect(self.generate_pack)

        self._populate_pack_selectors()

        self.refresh()

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
        data = fetch_latest_prompts(limit=limit)

        self.table.setRowCount(len(data))
        for i, row in enumerate(data):
            self.table.setItem(i, 0, QTableWidgetItem(str(row.id)))
            self.table.setItem(i, 1, QTableWidgetItem(row.category))
            self.table.setItem(i, 2, QTableWidgetItem(row.variant))
            self.table.setItem(i, 3, QTableWidgetItem(row.status))
            self.table.setItem(i, 4, QTableWidgetItem(row.title))
            self.table.setItem(i, 5, QTableWidgetItem("✅" if row.has_base else "—"))
            self.table.setItem(i, 6, QTableWidgetItem("✅" if row.has_upscale else "—"))

        self.table.resizeColumnsToContents()

        # Recalcular botones + preview tras refrescar
        self.update_actions_state()

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
        """
        which: 'base' or 'up'
        """
        if which == "base":
            self._base_path = path
        else:
            self._up_path = path

        if which == "base":
            img_label = self.base_image_label
            path_label = self.base_path_label
            self._pix_base = None
        else:
            img_label = self.up_image_label
            path_label = self.up_path_label
            self._pix_up = None

        if not path:
            path_label.setText("—")
            img_label.setText("(sin imagen)")
            img_label.setPixmap(QPixmap())
            return

        path_label.setText(str(path))

        if not path.exists():
            img_label.setText("(archivo no existe)")
            img_label.setPixmap(QPixmap())
            return

        pix = QPixmap(str(path))
        if pix.isNull():
            img_label.setText("(no se pudo cargar)")
            img_label.setPixmap(QPixmap())
            return

        if which == "base":
            self._pix_base = pix
        else:
            self._pix_up = pix

        self._rescale_previews()

    def _rescale_previews(self) -> None:
        # Base
        if self._pix_base and not self._pix_base.isNull():
            target = self.base_image_label.size()
            scaled = self._pix_base.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.base_image_label.setPixmap(scaled)
            self.base_image_label.setText("")
        else:
            if not self.base_image_label.pixmap():
                self.base_image_label.setText("(sin base)")

        # Upscale
        if self._pix_up and not self._pix_up.isNull():
            target = self.up_image_label.size()
            scaled = self._pix_up.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.up_image_label.setPixmap(scaled)
            self.up_image_label.setText("")
        else:
            if not self.up_image_label.pixmap():
                self.up_image_label.setText("(sin upscale)")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale_previews()

    # -------- Selection: enable actions + update preview --------

    def update_actions_state(self) -> None:
        """
        Habilita/deshabilita botones según si el item seleccionado tiene outputs guardados.
        Además actualiza el preview base/upscale.
        """
        pid = self._selected_prompt_id()
        if pid is None:
            self.open_base_btn.setEnabled(False)
            self.open_up_btn.setEnabled(False)
            self.open_folder_base_btn.setEnabled(False)
            self.open_folder_up_btn.setEnabled(False)
            self._set_preview(which="base", path=None)
            self._set_preview(which="up", path=None)
            return

        with get_connection() as conn:
            r = conn.execute(
                "SELECT base_image_json, upscale_image_json FROM prompt_item WHERE id=?",
                (pid,),
            ).fetchone()

        has_base = bool(r and r["base_image_json"])
        has_up = bool(r and r["upscale_image_json"])

        self.open_base_btn.setEnabled(has_base)
        self.open_folder_base_btn.setEnabled(has_base)
        self.open_up_btn.setEnabled(has_up)
        self.open_folder_up_btn.setEnabled(has_up)

        base_path: Path | None = None
        up_path: Path | None = None

        if r and r["base_image_json"]:
            base = json.loads(r["base_image_json"])
            base_path = build_output_path(base)

        if r and r["upscale_image_json"]:
            up = json.loads(r["upscale_image_json"])
            up_path = build_output_path(up)

        self._set_preview(which="base", path=base_path)
        self._set_preview(which="up", path=up_path)

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
        self.worker_thread.wait(3000)  # 3s

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
        # refresco ligero: solo refresh completo por ahora
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
        path = self._base_path if which == "base" else self._up_path
        if not path or not path.exists():
            QMessageBox.information(self, "Preview", "No hay imagen disponible para ampliar.")
            return

        title = "Preview Base" if which == "base" else "Preview Upscale"
        dlg = ImageViewer(title, path)
        dlg.exec()
