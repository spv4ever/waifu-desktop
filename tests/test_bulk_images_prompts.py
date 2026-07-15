import json

from app.config.bulk_images_prompts import load_bulk_image_prompts


def test_load_bulk_image_prompts_sorts_by_taxonomy_and_priority(tmp_path):
    path = tmp_path / "bulk_images_prompts.json"
    path.write_text(
        json.dumps(
            {
                "prompts": [
                    {
                        "id": "b",
                        "title": "Second",
                        "category": "Fashion",
                        "subcategory": "Studio",
                        "priority": 20,
                    },
                    {
                        "id": "a",
                        "title": "First",
                        "category": "Fashion",
                        "subcategory": "Studio",
                        "priority": 10,
                    },
                    {
                        "id": "c",
                        "title": "Third",
                        "category": "Character",
                        "subcategory": "Hero",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    prompts = load_bulk_image_prompts(path)

    assert [prompt.id for prompt in prompts] == ["c", "a", "b"]
    assert prompts[0].subcategory == "Hero"
    assert prompts[1].enabled is True
    assert prompts[1].status == "draft"
