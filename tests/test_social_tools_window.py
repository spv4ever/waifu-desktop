from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = qt_widgets.QApplication

from app.ui import social_tools_window


def test_selected_title_and_description_can_be_copied(monkeypatch):
    app = QApplication.instance() or QApplication([])
    post = SimpleNamespace(
        platform="x",
        title="Un título para copiar",
        description="Una descripción para copiar",
        author="Autora",
        assets=[],
        created_at="2026-08-12",
    )
    service = SimpleNamespace(list_posts=lambda: [post])
    monkeypatch.setattr(social_tools_window, "SocialMediaService", lambda: service)

    window = social_tools_window.SocialToolsWindow()
    window.table.selectRow(0)
    app.processEvents()

    assert window.copy_title_btn.isEnabled()
    assert window.copy_description_btn.isEnabled()

    window.copy_selected_title()
    assert QApplication.clipboard().text() == post.title
    assert window.status_label.text() == "Título copiado al portapapeles."

    window.copy_selected_description()
    assert QApplication.clipboard().text() == post.description
    assert window.status_label.text() == "Descripción copiada al portapapeles."

    window.close()
