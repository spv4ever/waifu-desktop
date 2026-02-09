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

    # Cloudinary (dollimages uploads)
    cloudinary_cloud_name: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    cloudinary_api_key: str = os.getenv("CLOUDINARY_API_KEY", "")
    cloudinary_api_secret: str = os.getenv("CLOUDINARY_API_SECRET", "")
    cloudinary_dollimages_folder: str = os.getenv("CLOUDINARY_DOLLIMAGES_FOLDER", "dollimages")
    dollimages_version: str = os.getenv("DOLLIMAGES_VERSION", "")

    # Cloudinary (waifu uploads)
    cloudinary_waifu_cloud_name: str = os.getenv("CLOUDINARY_WAIFU_CLOUD_NAME", "")
    cloudinary_waifu_api_key: str = os.getenv("CLOUDINARY_WAIFU_API_KEY", "")
    cloudinary_waifu_api_secret: str = os.getenv("CLOUDINARY_WAIFU_API_SECRET", "")
    cloudinary_waifu_folder: str = os.getenv("CLOUDINARY_WAIFU_FOLDER", "waifu")
    waifu_version: str = os.getenv("WAIFU_VERSION", "")

settings = Settings()
