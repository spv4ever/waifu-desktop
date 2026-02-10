from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.config.app_config import load_app_config


class WorkflowService:
    def __init__(self) -> None:
        self.cfg = load_app_config()

    def load_template(self, *, workflow_key: str = "waifu") -> dict[str, Any]:
        env_key = "COMFYUI_WORKFLOW_JSON"
        default_path = "resources/workflows/waifu_workflow.json"
        if workflow_key == "dollimages":
            env_key = "COMFYUI_WORKFLOW_DOLLIMAGES_JSON"
            default_path = "resources/workflows/dollimages.json"
        elif workflow_key == "dollimagesz":
            env_key = "COMFYUI_WORKFLOW_DOLLIMAGESZ_JSON"
            default_path = "resources/workflows/dollimagesz.json"
        elif workflow_key == "image2vid":
            env_key = "COMFYUI_WORKFLOW_IMAGE2VID_JSON"
            default_path = "resources/workflows/image2vid.json"

        path = Path(settings.__dict__.get("comfyui_workflow_json", ""))  # por si lo añades luego
        # Usamos .env directamente para no depender de settings si aún no lo añadiste:
        path = Path(__import__("os").getenv(env_key, default_path))
        return json.loads(path.read_text(encoding="utf-8"))

    def apply_overrides(
            self,
            workflow: dict[str, Any],
            *,
            prompt_text: str,
            negative_text: str,
            seed: int | None,
            steps: int | None,
            width: int | None,
            height: int | None,
            filename_prefix_base: str,
            filename_prefix_upscale: str,
            checkpoint_base: str | None,
            checkpoint_refiner: str | None,
            load_image: str | None = None,
            faceswap_enabled: bool | None = None,
            mapping_key: str = "comfyui_workflow",
        ) -> dict[str, Any]:
        """
        Aplica cambios a nodos según el mapping en app_config.yaml.
        """
        mapping = self.cfg.raw.get(mapping_key, {})
        # En ComfyUI, los nodos suelen estar en workflow["nodes"] o directamente como dict con keys string.
        # Normalmente el export es un dict donde cada node_id es una key.
        # Ej: workflow["10"]["inputs"]["text"] = ...
        # Aquí asumimos formato: { "10": { "inputs": {...} }, ... }
        def set_input(node_id: str, input_name: str, value: Any) -> None:
            node = workflow.get(str(node_id))
            if not node:
                raise KeyError(f"No existe node_id={node_id} en el workflow JSON")
            inputs = node.get("inputs")
            if inputs is None:
                raise KeyError(f"node_id={node_id} no tiene 'inputs'")
            inputs[input_name] = value

        def set_input_for_nodes(node_ids: str | list[str], input_name: str, value: Any) -> None:
            ids = [node_ids] if isinstance(node_ids, str) else node_ids
            for node_id in ids:
                set_input(node_id, input_name, value)

        ##mapping = self.cfg.raw.get("comfyui_workflow", {})
        defaults = self.cfg.raw.get("defaults", {})
        lock_steps = bool(defaults.get("lock_steps", False))

        if not lock_steps and steps is not None and mapping.get("steps"):
            set_input_for_nodes(mapping["steps"]["node_id"], mapping["steps"]["input"], int(steps))

        if mapping.get("prompt_pos"):
            set_input_for_nodes(mapping["prompt_pos"]["node_id"], mapping["prompt_pos"]["input"], prompt_text)
        if mapping.get("prompt_neg"):
            set_input_for_nodes(mapping["prompt_neg"]["node_id"], mapping["prompt_neg"]["input"], negative_text)

        if seed is not None and mapping.get("seed"):
            set_input_for_nodes(mapping["seed"]["node_id"], mapping["seed"]["input"], int(seed))

        if width is not None and mapping.get("width"):
            set_input_for_nodes(mapping["width"]["node_id"], mapping["width"]["input"], int(width))
        if height is not None and mapping.get("height"):
            set_input_for_nodes(mapping["height"]["node_id"], mapping["height"]["input"], int(height))

        if mapping.get("output_base"):
            set_input_for_nodes(mapping["output_base"]["node_id"], mapping["output_base"]["input"], filename_prefix_base)
        if mapping.get("output_upscale"):
            set_input_for_nodes(
                mapping["output_upscale"]["node_id"],
                mapping["output_upscale"]["input"],
                filename_prefix_upscale,
            )

        if checkpoint_base and mapping.get("checkpoint_base"):
            set_input_for_nodes(
                mapping["checkpoint_base"]["node_id"],
                mapping["checkpoint_base"]["input"],
                checkpoint_base,
            )

        if checkpoint_refiner and mapping.get("checkpoint_refiner"):
            set_input_for_nodes(
                mapping["checkpoint_refiner"]["node_id"],
                mapping["checkpoint_refiner"]["input"],
                checkpoint_refiner,
            )

        if load_image and mapping.get("load_image"):
            set_input_for_nodes(
                mapping["load_image"]["node_id"],
                mapping["load_image"]["input"],
                load_image,
            )

        if faceswap_enabled is not None and mapping.get("faceswap_enabled"):
            set_input_for_nodes(
                mapping["faceswap_enabled"]["node_id"],
                mapping["faceswap_enabled"]["input"],
                bool(faceswap_enabled),
            )

        return workflow
