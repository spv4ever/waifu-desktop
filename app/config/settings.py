from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

# Carga automática del .env
load_dotenv()


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("resources") / "data"
    db_path: Path = data_dir / "waifu_desktop.sqlite3"

    # ComfyUI (desde .env)
    comfyui_base_url: str = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    comfyui_poll_interval: float = float(os.getenv("COMFYUI_POLL_INTERVAL", "1.0"))
    comfyui_request_timeout: int = int(os.getenv("COMFYUI_REQUEST_TIMEOUT", "120"))
    comfyui_output_dir: str = os.getenv("COMFYUI_OUTPUT_DIR", "output")
    comfyui_checkpoints_dir: str = os.getenv("COMFYUI_CHECKPOINTS_DIR", "")

    # Worker
    queue_max_in_flight: int = int(os.getenv("QUEUE_MAX_IN_FLIGHT", "1"))


settings = Settings()
