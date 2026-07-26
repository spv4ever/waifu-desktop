from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.config.undress import UNDRESS_GARMENTS, UNDRESS_PROMPT_TEMPLATE


def test_undress_workflow_mappings_target_existing_nodes() -> None:
    workflow = json.loads(Path("resources/workflows/undress.json").read_text(encoding="utf-8"))
    config = yaml.safe_load(Path("resources/config/app_config.yaml").read_text(encoding="utf-8"))
    mapping = config["comfyui_workflow_undress"]

    assert workflow[mapping["load_image"]["node_id"]]["class_type"] == "LoadImage"
    assert workflow[mapping["prompt_pos"]["node_id"]]["class_type"] == "CLIPTextEncode"
    assert workflow[mapping["output_base"]["node_id"]]["class_type"] == "VHS_VideoCombine"
    assert workflow["63"]["inputs"]["start_image"] == [mapping["load_image"]["node_id"], 0]


def test_undress_prompt_only_substitutes_the_selected_garment() -> None:
    prompts = [UNDRESS_PROMPT_TEMPLATE.format(garment=garment) for garment in UNDRESS_GARMENTS]

    assert len(set(prompts)) == len(UNDRESS_GARMENTS)
    assert "tears apart her shirt and pants" in prompts[-1]
    assert all("Masturbating, showing her pussy, \nShe seductively" in prompt for prompt in prompts)
