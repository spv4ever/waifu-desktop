from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea


class ImageViewer(QDialog):
    def __init__(self, title: str, image_path: Path) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1100, 800)

        layout = QVBoxLayout(self)

        self.path_label = QLabel(str(image_path))
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.path_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.image_label)

        pix = QPixmap(str(image_path))
        self.image_label.setPixmap(pix)
