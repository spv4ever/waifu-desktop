from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = qt_widgets.QApplication

from app.ui.qr_code_window import QrCodeWindow


def test_qr_window_generates_preview_and_copies_image():
    app = QApplication.instance() or QApplication([])
    window = QrCodeWindow()
    window.url_input.setText("example.com/new")

    window.generate_btn.click()
    app.processEvents()

    assert window.normalized_url == "https://example.com/new"
    assert window.preview.pixmap() is not None
    assert window.save_btn.isEnabled()
    assert window.copy_btn.isEnabled()

    window.copy_btn.click()
    assert not QApplication.clipboard().image().isNull()
    assert window.status.text() == "Código QR copiado al portapapeles."
    window.close()
