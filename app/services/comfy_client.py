from __future__ import annotations

import requests
from typing import Any

from app.config.settings import settings


class ComfyClient:
    def __init__(self) -> None:
        self.base_url = settings.comfyui_base_url.rstrip("/")
        self.timeout = settings.comfyui_request_timeout

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
