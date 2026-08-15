from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from app.ui.main_window import MainWindow


class _Combo:
    def __init__(self, data=None, text=""):
        self._data = data
        self._text = text

    def currentData(self):
        return self._data

    def currentText(self):
        return self._text


class _Spin:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _Label:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


def test_bulk_youtube_plan_accepts_one_audio():
    calls = []
    plan = SimpleNamespace(
        audio_duration_seconds=180.0,
        image_display_seconds=8.0,
        transition_seconds=0.75,
        needed_images=25,
        available_images=30,
    )
    window = SimpleNamespace(
        bulk_youtube_plan_label=_Label(),
        bulk_youtube_category_combo=_Combo("Nature Wallpaper"),
        bulk_youtube_audio_combo=_Combo("rain.mp3"),
        bulk_youtube_second_audio_combo=_Combo(None),
        bulk_youtube_seconds_spin=_Spin(8.0),
        bulk_youtube_transition_spin=_Spin(0.75),
        bulk_youtube_transition_type_combo=_Combo("fade", "Fundido"),
        video_montage_service=SimpleNamespace(
            calculate_bulk_youtube_plan=lambda **kwargs: calls.append(kwargs) or plan
        ),
    )

    MainWindow._update_bulk_youtube_plan_label(window)

    assert calls[0]["audio_filename"] == "rain.mp3"
    assert calls[0]["second_audio_filename"] is None
    assert "Necesitas: 25 imágenes" in window.bulk_youtube_plan_label.text
