import random

from app.config.waifu_catalog import load_waifu_catalog
from app.services.waifu_prompt_builder import _build_combination_prompt


def test_catalog_offers_normal_and_fantasy_combinations(monkeypatch):
    monkeypatch.setattr(
        "app.config.waifu_catalog.get_store",
        lambda: _CatalogStoreStub(),
    )

    combinations = load_waifu_catalog().combinations

    assert combinations["normal"]["label"] == "Combinación normal"
    assert combinations["fantasy"]["label"] == "Combinación fantasía"
    assert len(combinations["fantasy"]["options"]) >= 2


def test_fantasy_combination_picks_one_kind_of_fantasy_woman():
    config = {
        "prompt": "adult fantasy woman, magical heroine",
        "pick_count": 1,
        "options": ["elven woman", "fairy woman", "sorceress woman"],
    }

    prompt = _build_combination_prompt(random.Random(4), config)

    assert prompt.startswith("adult fantasy woman, magical heroine, ")
    assert sum(option in prompt for option in config["options"]) == 1


class _CatalogStoreStub:
    def ensure_prompt_base_seeded(self, _categories):
        return None

    def ensure_prompt_variations_seeded(self, _data):
        return None

    def list_prompt_bases(self, *, include_disabled):
        assert include_disabled is False
        return []

    def fetch_prompt_variations_tree(self):
        return {}
