from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from app.config.settings import settings


class ComfyClient:
    def __init__(self, *, base_url: str | None = None) -> None:
        resolved_base_url = base_url or settings.comfyui_base_url
        self.base_url = resolved_base_url.rstrip("/")
        self.timeout = settings.comfyui_request_timeout

    def upload_image(self, image_path: str | Path, *, overwrite: bool = True) -> str:
        """Upload an image to this ComfyUI instance and return its LoadImage name."""
        path = Path(image_path)
        url = f"{self.base_url}/upload/image"
        with path.open("rb") as image_file:
            response = requests.post(
                url,
                files={"image": (path.name, image_file)},
                data={"type": "input", "overwrite": str(overwrite).lower()},
                timeout=self.timeout,
            )
        if not response.ok:
            raise RuntimeError(
                f"ComfyUI /upload/image error {response.status_code}: {response.text}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"ComfyUI devolvió una respuesta no JSON al subir la imagen: {response.text}"
            ) from exc

        name = str(payload.get("name") or "").strip()
        if not name:
            raise RuntimeError(f"ComfyUI no devolvió el nombre de la imagen subida: {payload}")
        subfolder = str(payload.get("subfolder") or "").strip().strip("/\\")
        return f"{subfolder}/{name}" if subfolder else name

    def submit_prompt(self, workflow: dict[str, Any]) -> str:
        """
        POST /prompt
        Esperamos algo tipo: {"prompt_id":"...","number":...}
        """
        url = f"{self.base_url}/prompt"
        r = requests.post(url, json={"prompt": workflow}, timeout=self.timeout)
        if not r.ok:
            raise RuntimeError(f"ComfyUI /prompt error {r.status_code}: {r.text}")
        try:
            data = r.json()
        except ValueError as exc:
            raise RuntimeError(f"ComfyUI devolvió respuesta no JSON: {r.text}") from exc
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI no devolvió prompt_id. Respuesta: {data}")
        return str(prompt_id)

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/history/{prompt_id}"
        r = requests.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_queue(self) -> dict[str, Any]:
        url = f"{self.base_url}/queue"
        r = requests.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def is_prompt_in_queue(self, prompt_id: str) -> bool:
        queue = self.get_queue()

        def _contains_prompt_id(value: Any) -> bool:
            if isinstance(value, dict):
                return any(_contains_prompt_id(v) for v in value.values())
            if isinstance(value, (list, tuple)):
                return any(_contains_prompt_id(v) for v in value)
            return str(value) == prompt_id

        running = queue.get("queue_running")
        pending = queue.get("queue_pending")
        return _contains_prompt_id(running) or _contains_prompt_id(pending)
