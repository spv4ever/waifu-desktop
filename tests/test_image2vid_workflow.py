from __future__ import annotations

import json
from pathlib import Path

import yaml


def test_image2vid_uses_comfyui_load_image_node_for_local_inputs() -> None:
    workflow = json.loads(Path("resources/workflows/image2vid.json").read_text(encoding="utf-8"))
    config = yaml.safe_load(Path("resources/config/app_config.yaml").read_text(encoding="utf-8"))

    load_image_mapping = config["comfyui_workflow_image2vid"]["load_image"]
    load_image_node_id = load_image_mapping["node_id"]

    assert load_image_node_id == "97"
    assert workflow[load_image_node_id]["class_type"] == "LoadImage"
    assert workflow["98"]["inputs"]["start_image"] == [load_image_node_id, 0]


def test_undress_has_video_workflow_mappings_and_fixed_dimensions() -> None:
    workflow = json.loads(Path("resources/workflows/undress.json").read_text(encoding="utf-8"))
    config = yaml.safe_load(Path("resources/config/app_config.yaml").read_text(encoding="utf-8"))
    mapping = config["comfyui_workflow_undress"]

    assert workflow[mapping["load_image"]["node_id"]]["class_type"] == "LoadImage"
    assert workflow[mapping["prompt_pos"]["node_id"]]["inputs"][mapping["prompt_pos"]["input"]]
    assert workflow["98"]["inputs"]["width"] == 480
    assert workflow["98"]["inputs"]["height"] == 720
