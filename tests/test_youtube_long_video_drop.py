from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_core = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = qt_widgets.QApplication
QMimeData = qt_core.QMimeData
QUrl = qt_core.QUrl

from app.ui.main_window import VideoDropLineEdit


def test_youtube_long_drop_field_accepts_a_local_video(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    video = tmp_path / "source.MP4"
    video.write_bytes(b"video")
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(video))])

    field = VideoDropLineEdit()

    assert field._video_path_from_mime(mime_data) == video


def test_youtube_long_drop_field_rejects_non_video_files(tmp_path: Path) -> None:
    QApplication.instance() or QApplication([])
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not a video", encoding="utf-8")
    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(text_file))])

    field = VideoDropLineEdit()

    assert field._video_path_from_mime(mime_data) is None
