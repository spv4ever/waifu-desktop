from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.config.undress import (
    UNDRESS_GARMENTS,
    build_undress_prompt,
    calculate_undress_duration,
)
from app.services.workflow_service import WorkflowService


def test_undress_workflow_mappings_target_existing_nodes() -> None:
    workflow = json.loads(Path("resources/workflows/undress.json").read_text(encoding="utf-8"))
    config = yaml.safe_load(Path("resources/config/app_config.yaml").read_text(encoding="utf-8"))
    mapping = config["comfyui_workflow_undress"]

    assert workflow[mapping["load_image"]["node_id"]]["class_type"] == "LoadImage"
    assert workflow[mapping["prompt_pos"]["node_id"]]["class_type"] == "CLIPTextEncode"
    assert workflow[mapping["output_base"]["node_id"]]["class_type"] == "VHS_VideoCombine"
    assert workflow["63"]["inputs"]["start_image"] == [mapping["load_image"]["node_id"], 0]
    fixed_prompt = workflow[mapping["prompt_pos"]["node_id"]]["inputs"]["text"]
    assert "Masturbating, showing her pussy" not in fixed_prompt
    assert "tears apart her dress then pulls it down to fall away" in fixed_prompt


def test_undress_prompt_only_substitutes_the_selected_garment() -> None:
    prompts = [build_undress_prompt([garment]) for garment in UNDRESS_GARMENTS]

    assert len(set(prompts)) == len(UNDRESS_GARMENTS)
    assert "tears apart her shirt and pants then pulls it down to fall away" in prompts[-1]
    assert all("Masturbating, showing her pussy" not in prompt for prompt in prompts)


def test_undress_prompt_lists_checked_garments_in_one_action() -> None:
    prompt = build_undress_prompt(["panties", "t-shirt", "skirt"])

    assert (
        "effortlessly tears apart her panties, t-shirt, skirt "
        "then pulls it down to fall away"
    ) in prompt
    assert prompt.count("then pulls it down to fall away") == 1


def test_undress_garments_include_requested_bikini_options() -> None:
    assert "bikini" in UNDRESS_GARMENTS
    assert "bikini buttom" in UNDRESS_GARMENTS


def test_undress_prompt_uses_default_when_no_garment_is_checked() -> None:
    assert "tears apart her dress" in build_undress_prompt([])


def test_undress_duration_scales_with_accumulated_garments() -> None:
    assert calculate_undress_duration(["dress"]) == (4.0, 97)
    assert calculate_undress_duration(["dress", "bra"]) == (8.0, 193)
    assert calculate_undress_duration(["dress", "bra", "panties"]) == (12.0, 289)


def test_undress_duration_uses_one_garment_when_selection_is_empty() -> None:
    assert calculate_undress_duration([]) == (4.0, 97)


def test_undress_workflow_receives_scaled_video_length() -> None:
    workflow = json.loads(Path("resources/workflows/undress.json").read_text(encoding="utf-8"))

    updated = WorkflowService().apply_overrides(
        workflow,
        prompt_text="prompt",
        negative_text="negative",
        seed=123,
        steps=None,
        width=480,
        height=768,
        length=193,
        filename_prefix_base="undress/test",
        filename_prefix_upscale="",
        checkpoint_base=None,
        checkpoint_refiner=None,
        load_image="source.png",
        mapping_key="comfyui_workflow_undress",
    )

    assert updated["63"]["inputs"]["length"] == 193
