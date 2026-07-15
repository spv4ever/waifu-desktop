import json

from app.config.bulk_images_prompts import (
    bulk_image_prompts_example_payload,
    import_bulk_image_prompts,
    load_bulk_image_prompts,
)


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
    assert prompts[1].quantity == 1



def test_import_bulk_image_prompts_adds_and_updates_by_id(tmp_path):
    destination = tmp_path / "bulk_images_prompts.json"
    destination.write_text(
        json.dumps(
            {
                "library_name": "Bulk Images",
                "prompts": [
                    {
                        "id": "existing",
                        "title": "Old title",
                        "positive_prompt": "old prompt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    import_file = tmp_path / "import.json"
    import_file.write_text(
        json.dumps(
            {
                "prompts": [
                    {
                        "id": "existing",
                        "title": "Updated title",
                        "positive_prompt": "updated prompt",
                    },
                    {
                        "id": "new",
                        "title": "New title",
                        "positive_prompt": "new prompt",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    added, updated = import_bulk_image_prompts(import_file, destination)

    assert (added, updated) == (1, 1)
    prompts = {prompt.id: prompt for prompt in load_bulk_image_prompts(destination)}
    assert prompts["existing"].title == "Updated title"
    assert prompts["new"].positive_prompt == "new prompt"


def test_bulk_image_prompts_example_payload_matches_import_format(tmp_path):
    import_file = tmp_path / "example.json"
    destination = tmp_path / "bulk_images_prompts.json"
    import_file.write_text(json.dumps(bulk_image_prompts_example_payload()), encoding="utf-8")

    added, updated = import_bulk_image_prompts(import_file, destination)

    assert (added, updated) == (1, 0)
    prompts = load_bulk_image_prompts(destination)
    assert prompts[0].id == "bulk-example-001"
    assert prompts[0].enabled is True
    assert prompts[0].quantity == 3


def test_import_bulk_image_prompts_persists_to_database_by_default(tmp_path):
    from app.config.settings import settings

    old_data_dir = settings.data_dir
    old_db_path = settings.db_path
    object.__setattr__(settings, "data_dir", tmp_path)
    object.__setattr__(settings, "db_path", tmp_path / "bulk.sqlite3")
    try:
        import_file = tmp_path / "import_db.json"
        import_file.write_text(
            json.dumps(
                {
                    "prompts": [
                        {"id": "db-1", "title": "DB prompt", "positive_prompt": "first"},
                        {"id": "db-2", "title": "Second DB prompt", "positive_prompt": "second", "enabled": False},
                    ]
                }
            ),
            encoding="utf-8",
        )

        added, updated = import_bulk_image_prompts(import_file)

        assert (added, updated) == (2, 0)
        prompts = {prompt.id: prompt for prompt in load_bulk_image_prompts()}
        assert prompts["db-1"].title == "DB prompt"
        assert prompts["db-2"].enabled is False
    finally:
        object.__setattr__(settings, "data_dir", old_data_dir)
        object.__setattr__(settings, "db_path", old_db_path)
