import json
from pathlib import Path

import pytest

from app.config.bulk_images_prompts import load_bulk_image_prompts


CATALOG_DIR = Path("resources/config/bulk_images_prompts")
EXPECTED_CATALOGS = {
    "summer.json": "Summer",
    "bikinis.json": "Bikinis",
    "snow.json": "Snow",
    "saunas.json": "Saunas",
    "iconic_travel.json": "Iconic Travel",
}


@pytest.mark.parametrize(("filename", "collection"), EXPECTED_CATALOGS.items())
def test_thematic_bulk_catalog_is_importable(filename: str, collection: str) -> None:
    path = CATALOG_DIR / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    prompts = load_bulk_image_prompts(path)

    assert payload["version"] == 1
    assert len(prompts) >= 6
    assert all(prompt.collection == collection for prompt in prompts)
    assert all(prompt.id and prompt.title and prompt.positive_prompt for prompt in prompts)
    assert all(prompt.status == "ready" and prompt.enabled for prompt in prompts)


def test_thematic_bulk_catalog_ids_are_unique() -> None:
    ids = [
        prompt.id
        for filename in EXPECTED_CATALOGS
        for prompt in load_bulk_image_prompts(CATALOG_DIR / filename)
    ]

    assert len(ids) == len(set(ids))
