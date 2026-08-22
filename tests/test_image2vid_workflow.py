from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.services.workflow_service import WorkflowService


IMAGE2VID_ADDITIONAL_NEGATIVE_PROMPT = (
    "distorted hands, fused fingers, deformed bodies, robotic or jerky movements, drastic anatomy changes, "
    "unnatural skin textures, unrealistic breast shapes, extra limbs, floating body parts, loss of coherence, "
    "sudden pose changes, blurry face"
)


def test_image2vid_uses_comfyui_load_image_node_for_local_inputs() -> None:
    workflow = json.loads(Path("resources/workflows/image2vid.json").read_text(encoding="utf-8"))
    config = yaml.safe_load(Path("resources/config/app_config.yaml").read_text(encoding="utf-8"))

    load_image_mapping = config["comfyui_workflow_image2vid"]["load_image"]
    load_image_node_id = load_image_mapping["node_id"]

    assert load_image_node_id == "97"
    assert workflow[load_image_node_id]["class_type"] == "LoadImage"
    assert workflow["98"]["inputs"]["start_image"] == [load_image_node_id, 0]


def test_image2vid_template_includes_additional_negative_prompt() -> None:
    workflow = json.loads(Path("resources/workflows/image2vid.json").read_text(encoding="utf-8"))

    assert IMAGE2VID_ADDITIONAL_NEGATIVE_PROMPT in workflow["89"]["inputs"]["text"]


def test_image2vid_overrides_force_high_and_low_noise_loras_on() -> None:
    service = WorkflowService()
    workflow = service.load_template(workflow_key="image2vid")
    # Simulate a workflow exported after both rgthree toggles were switched off.
    workflow["115"]["inputs"]["lora_2"]["on"] = False
    workflow["116"]["inputs"]["lora_2"]["on"] = False

    updated = service.apply_overrides(
        workflow,
        prompt_text="move",
        negative_text="",
        seed=123,
        steps=None,
        width=480,
        height=720,
        length=81,
        filename_prefix_base="image2vid/test",
        filename_prefix_upscale="image2vid/test",
        checkpoint_base=None,
        checkpoint_refiner=None,
        load_image="source.png",
        mapping_key="comfyui_workflow_image2vid",
    )

    assert updated["115"]["inputs"]["lora_2"] == {
        "on": True,
        "lora": "wan\\NSFWWAN22H_nsfwsks.safetensors",
        "strength": 1.0,
    }
    assert updated["116"]["inputs"]["lora_2"] == {
        "on": True,
        "lora": "wan\\NSFWWAN22L_nsfwsks.safetensors",
        "strength": 1.0,
    }


def test_image2vid_noise_loras_feed_the_matching_sampler_branches() -> None:
    workflow = json.loads(Path("resources/workflows/image2vid.json").read_text(encoding="utf-8"))

    assert workflow["104"]["inputs"]["model"] == ["115", 0]
    assert workflow["103"]["inputs"]["model"] == ["116", 0]
    assert workflow["114"]["inputs"]["model_high_noise"] == ["104", 0]
    assert workflow["114"]["inputs"]["model_low_noise"] == ["103", 0]
