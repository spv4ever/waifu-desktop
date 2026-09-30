from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.qr_code_service import InvalidQrUrl, QrCodeService


class QrCodeWindow(QMainWindow):
    """Simple QR generator for web links."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Waifu Desktop — Generador de códigos QR")
        self.setMinimumSize(620, 700)
        self.resize(680, 760)
        self.service = QrCodeService()
        self.png_data: bytes | None = None
        self.normalized_url = ""

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Generador de códigos QR")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Pega un enlace y genera un QR estándar, limpio y listo para guardar o copiar."
        )
        subtitle.setObjectName("AppSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        input_group = QGroupBox("Enlace")
        input_layout = QVBoxLayout(input_group)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://ejemplo.com")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.returnPressed.connect(self.generate_qr)
        input_layout.addWidget(self.url_input)
        self.generate_btn = QPushButton("Generar código QR")
        self.generate_btn.setObjectName("PrimaryButton")
        self.generate_btn.clicked.connect(self.generate_qr)
        input_layout.addWidget(self.generate_btn, alignment=Qt.AlignRight)
        layout.addWidget(input_group)

        preview_group = QGroupBox("Vista previa")
        preview_layout = QVBoxLayout(preview_group)
        self.preview = QLabel("Tu código QR aparecerá aquí")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(420, 420)
        self.preview.setObjectName("QrPreview")
        preview_layout.addWidget(self.preview, alignment=Qt.AlignCenter)
        layout.addWidget(preview_group, 1)

        self.status = QLabel("Introduce un enlace para comenzar.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        actions = QHBoxLayout()
        self.copy_btn = QPushButton("Copiar QR")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self.copy_qr)
        self.save_btn = QPushButton("Guardar PNG…")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_qr)
        actions.addStretch()
        actions.addWidget(self.copy_btn)
        actions.addWidget(self.save_btn)
        layout.addLayout(actions)

        self.setStyleSheet(
            "QLabel#QrPreview { background: white; color: #64748b; "
            "border: 1px solid #cbd5e1; border-radius: 12px; padding: 16px; }"
        )

    def generate_qr(self) -> None:
        try:
            normalized_url, png_data = self.service.generate_png(self.url_input.text())
        except InvalidQrUrl as exc:
            self.png_data = None
            self.normalized_url = ""
            self.preview.clear()
            self.preview.setText("Revisa el enlace e inténtalo de nuevo")
            self.copy_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            self.status.setText(str(exc))
            return

        image = QImage.fromData(png_data, "PNG")
        pixmap = QPixmap.fromImage(image).scaled(
            390, 390, Qt.KeepAspectRatio, Qt.FastTransformation
        )
        self.png_data = png_data
        self.normalized_url = normalized_url
        self.preview.setPixmap(pixmap)
        self.url_input.setText(normalized_url)
        self.copy_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.status.setText(f"QR generado correctamente para: {normalized_url}")

    def copy_qr(self) -> None:
        if not self.png_data:
            return
        image = QImage.fromData(self.png_data, "PNG")
        QApplication.clipboard().setImage(image)
        self.status.setText("Código QR copiado al portapapeles.")

    def save_qr(self) -> None:
        if not self.png_data:
            return
        suggested_name = "codigo-qr.png"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Guardar código QR", suggested_name, "Imagen PNG (*.png)"
        )
        if not filename:
            return
        try:
            path = self.service.save_png(self.png_data, filename)
        except OSError as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.status.setText(f"Código QR guardado en: {Path(path)}")
