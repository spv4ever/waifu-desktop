from __future__ import annotations

import os
from pathlib import Path
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


def test_share_x_notifies_that_published_images_changed(monkeypatch, tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    images = tuple(tmp_path / f"image-{index}.png" for index in range(4))
    draft = SimpleNamespace(
        images=images,
        compose_url="https://x.com/intent/post?text=test",
    )

    class FakeXShareService:
        def options(self):
            return {"anime": {"character": ["normal"]}}

        def create_draft(self, category, subcategory, version):
            return draft

        def mark_published(self, selected_draft):
            assert selected_draft is draft

    monkeypatch.setattr(social_tools_window, "XShareService", FakeXShareService)
    monkeypatch.setattr(
        social_tools_window, "SocialMediaService", lambda: SimpleNamespace(list_posts=lambda: [])
    )
    monkeypatch.setattr(social_tools_window.QDesktopServices, "openUrl", lambda _url: True)
    monkeypatch.setattr(social_tools_window.QMessageBox, "information", lambda *args: None)

    window = social_tools_window.SocialToolsWindow()
    notifications = []
    window.published_on_x_updated.connect(lambda: notifications.append(True))

    window.share_x()
    app.processEvents()

    assert notifications == [True]
    window.close()


def test_share_x_keeps_selected_filters_after_refresh(monkeypatch, tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    images = tuple(tmp_path / f"image-{index}.png" for index in range(4))
    draft = SimpleNamespace(images=images, compose_url="https://x.com/intent/post?text=test")

    class FakeXShareService:
        def options(self):
            return {
                "anime": {"character": ["normal"]},
                "waifu": {"beach": ["day", "night"]},
            }

        def create_draft(self, category, subcategory, version):
            assert (category, subcategory, version) == ("waifu", "beach", "night")
            return draft

        def mark_published(self, _draft):
            return None

    monkeypatch.setattr(social_tools_window, "XShareService", FakeXShareService)
    monkeypatch.setattr(
        social_tools_window, "SocialMediaService", lambda: SimpleNamespace(list_posts=lambda: [])
    )
    monkeypatch.setattr(social_tools_window.QDesktopServices, "openUrl", lambda _url: True)
    monkeypatch.setattr(social_tools_window.QMessageBox, "information", lambda *args: None)

    window = social_tools_window.SocialToolsWindow()
    window.x_category_combo.setCurrentIndex(window.x_category_combo.findData("waifu"))
    window.x_subcategory_combo.setCurrentIndex(window.x_subcategory_combo.findData("beach"))
    window.x_version_combo.setCurrentIndex(window.x_version_combo.findData("night"))

    window.share_x()
    app.processEvents()

    assert window.x_category_combo.currentData() == "waifu"
    assert window.x_subcategory_combo.currentData() == "beach"
    assert window.x_version_combo.currentData() == "night"
    window.close()
