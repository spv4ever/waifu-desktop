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
    comfyui_dollimages_base_url: str = os.getenv("COMFYUI_DOLLIMAGES_BASE_URL", "")
    comfyui_poll_interval: float = float(os.getenv("COMFYUI_POLL_INTERVAL", "1.0"))
    comfyui_request_timeout: int = int(os.getenv("COMFYUI_REQUEST_TIMEOUT", "120"))
    comfyui_history_wait_seconds: float = float(os.getenv("COMFYUI_HISTORY_WAIT_SECONDS", "180"))
    comfyui_output_dir: str = os.getenv("COMFYUI_OUTPUT_DIR", "output")
    comfyui_image2vid_output_dir: str = os.getenv("COMFYUI_IMAGE2VID_OUTPUT_DIR", "")
    comfyui_dollimages_output_dir: str = os.getenv("COMFYUI_DOLLIMAGES_OUTPUT_DIR", "")
    comfyui_input_dir: str = os.getenv("COMFYUI_INPUT_DIR", "input")
    comfyui_checkpoints_dir: str = os.getenv("COMFYUI_CHECKPOINTS_DIR", "")

    # Worker
    queue_max_in_flight: int = int(os.getenv("QUEUE_MAX_IN_FLIGHT", "1"))

    # Dollimages prompts
    dollimages_prompts_json: str = os.getenv(
        "DOLLIMAGES_PROMPTS_JSON",
        "resources/config/dollimages_prompts.json",
    )

    # Reel social handles (desde .env)
    reel_instagram_handle: str = os.getenv("REEL_INSTAGRAM_HANDLE", "@yourinstagram")
    reel_x_handle: str = os.getenv("REEL_X_HANDLE", "@yourx")
    reel_dollimages_handle: str = os.getenv("REEL_DOLLIMAGES_HANDLE", "@dollimages")
    reel_library_name: str = os.getenv("REEL_LIBRARY_NAME", "Library Waifu")


settings = Settings()
