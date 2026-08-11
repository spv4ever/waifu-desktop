from pathlib import Path


MAIN_WINDOW_SOURCE = Path("app/ui/main_window.py").read_text(encoding="utf-8")


def test_image2vid_exposes_disk_and_drag_reference_controls() -> None:
    assert 'self.image2vid_source_label = ImageDropLabel(' in MAIN_WINDOW_SOURCE
    assert 'self.image2vid_select_file_btn = QPushButton("Cargar desde disco")' in MAIN_WINDOW_SOURCE
    assert (
        "self.image2vid_select_file_btn.clicked.connect(self._set_image2vid_source_from_disk)"
        in MAIN_WINDOW_SOURCE
    )
    assert (
        "self.image2vid_source_label.imageDropped.connect(self._set_image2vid_source_from_drop)"
        in MAIN_WINDOW_SOURCE
    )


def test_image2vid_disk_picker_filters_supported_image_formats() -> None:
    assert '"Cargar imagen para Image2Vid"' in MAIN_WINDOW_SOURCE
    assert '"Imágenes (*.png *.jpg *.jpeg *.webp *.bmp);;Todos los archivos (*)"' in MAIN_WINDOW_SOURCE
    assert 'source_category="disco"' in MAIN_WINDOW_SOURCE
    assert 'source_category="arrastrada"' in MAIN_WINDOW_SOURCE
