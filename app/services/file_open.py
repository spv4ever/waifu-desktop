from __future__ import annotations

import os
import subprocess
from pathlib import Path


def open_file(path: Path) -> None:
    """
    Abre un archivo con el programa por defecto (Windows).
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    # Windows: abre con app por defecto
    os.startfile(str(path))  # type: ignore[attr-defined]


def open_folder_and_select(path: Path) -> None:
    """
    Abre el explorador y selecciona el archivo.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    # explorer /select, <path>
    subprocess.run(["explorer", "/select,", str(path)], check=False)
