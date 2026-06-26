from __future__ import annotations

from pathlib import Path

from app.config.app_config import load_app_config
from app.config.settings import settings
from app.services.workflow_service import WorkflowService


class CheckpointService:
    def __init__(self, *, checkpoints_dir: Path | None = None) -> None:
        if checkpoints_dir is not None:
            self._checkpoints_dir = checkpoints_dir
        else:
            env_dir = settings.comfyui_checkpoints_dir
            self._checkpoints_dir = Path(env_dir) if env_dir else None

    def list_available(self) -> list[str]:
        if not self._checkpoints_dir or not self._checkpoints_dir.is_dir():
            return []

        allowed_suffixes = {".safetensors", ".ckpt", ".pt", ".pth"}
        items = [
            path.name
            for path in self._checkpoints_dir.iterdir()
            if path.is_file() and path.suffix.lower() in allowed_suffixes
        ]
        return sorted(items, key=str.casefold)

    def get_default_checkpoints(self, *, workflow_key: str = "waifu", mapping_key: str = "comfyui_workflow") -> tuple[str | None, str | None]:
        workflow = WorkflowService().load_template(workflow_key=workflow_key)
        mapping = load_app_config().raw.get(mapping_key, {})

        def read_input(node_id: str | None, input_name: str | None) -> str | None:
            if not node_id or not input_name:
                return None
            node = workflow.get(str(node_id))
            if not node:
                return None
            inputs = node.get("inputs") or {}
            value = inputs.get(input_name)
            return str(value) if value else None

        base_cfg = mapping.get("checkpoint_base", {})
        refiner_cfg = mapping.get("checkpoint_refiner", {})

        base_name = read_input(base_cfg.get("node_id"), base_cfg.get("input"))
        refiner_name = read_input(refiner_cfg.get("node_id"), refiner_cfg.get("input"))

        return base_name, refiner_name
