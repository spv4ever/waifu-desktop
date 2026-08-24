from pathlib import Path


MAIN_WINDOW_SOURCE = Path("app/ui/main_window.py").read_text(encoding="utf-8")


def test_youtube_long_uses_a_video_drop_field() -> None:
    assert "class VideoDropLineEdit(QLineEdit):" in MAIN_WINDOW_SOURCE
    assert "self.repeat_video_path_input = VideoDropLineEdit()" in MAIN_WINDOW_SOURCE
    assert '"Arrastra un vídeo aquí o pulsa Elegir vídeo…"' in MAIN_WINDOW_SOURCE
