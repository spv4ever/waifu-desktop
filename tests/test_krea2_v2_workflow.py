import json
from pathlib import Path

from app.services.comfy_history_parser import extract_base_and_upscale
from app.services.workflow_service import WorkflowService


def test_krea2_v2_mapping_targets_existing_workflow_nodes(monkeypatch) -> None:
    monkeypatch.delenv("COMFYUI_WORKFLOW_KREA2_V2_JSON", raising=False)
    service = WorkflowService()
    workflow = service.load_template(workflow_key="krea2_v2")
    mapping = service.cfg.raw["comfyui_workflow_krea2_v2"]

    assert workflow == json.loads(
        Path("resources/workflows/krea2_v2.json").read_text(encoding="utf-8")
    )
    for field in ("prompt_pos", "seed", "width", "height", "output_base", "output_upscale"):
        assert mapping[field]["node_id"] in workflow


def test_krea2_v2_overrides_prompt_generation_and_output_nodes() -> None:
    service = WorkflowService()
    workflow = service.load_template(workflow_key="krea2_v2")

    result = service.apply_overrides(
        workflow,
        prompt_text="new prompt",
        negative_text="",
        seed=123,
        steps=None,
        width=704,
        height=528,
        length=None,
        filename_prefix_base="dollimages/sfw/1",
        filename_prefix_upscale="dollimages/sfw/1_upscaled",
        checkpoint_base=None,
        checkpoint_refiner=None,
        mapping_key="comfyui_workflow_krea2_v2",
    )

    assert result["408"]["inputs"]["value"] == "new prompt"
    assert result["31"]["inputs"]["seed"] == 123
    assert result["367"]["inputs"]["width"] == 704
    assert result["367"]["inputs"]["height"] == 528
    assert result["363"]["inputs"]["filename_prefix"] == "dollimages/sfw/1"
    assert result["364"]["inputs"]["filename_prefix"] == "dollimages/sfw/1_upscaled"


def test_krea2_v2_history_uses_its_base_and_upscale_save_nodes() -> None:
    base = {"filename": "base.png"}
    upscale = {"filename": "upscale.png"}
    entry = {
        "outputs": {
            "363": {"images": [base]},
            "364": {"images": [upscale]},
        }
    }

    assert extract_base_and_upscale(entry, workflow_key="krea2_v2") == (base, upscale)
