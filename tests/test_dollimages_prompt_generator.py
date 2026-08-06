import json
import random

import pytest

from app.services.dollimages_prompt_generator import (
    choose_dollimages_prompt_selection,
    fill_dollimages_prompt_tokens,
    load_dollimages_prompt_options,
    load_dollimages_fantasy_prompt_options,
)


def _options():
    return {
        "girl_types": ["a brunette woman"],
        "poses": ["standing confidently"],
        "outfits": ["a tailored dress"],
        "locations": ["on a rooftop"],
        "expressions": ["with a warm smile"],
        "lighting": ["golden-hour lighting"],
        "shots": ["full-body photograph"],
        "styles": ["fashion editorial photography"],
    }


def test_combination_prompt_has_characteristics_without_anime_tokens():
    selection = choose_dollimages_prompt_selection(random.Random(1), _options())
    prompt = fill_dollimages_prompt_tokens(
        "[girl_type], [shot], [pose], [outfit], [location], [expression], [lighting], [style]",
        selection,
    )

    assert prompt == (
        "a brunette woman, full-body photograph, standing confidently, a tailored dress, "
        "on a rooftop, with a warm smile, golden-hour lighting, fashion editorial photography"
    )
    assert "[personaje]" not in prompt
    assert "[anime]" not in prompt


def test_options_json_requires_every_combination_group(tmp_path):
    path = tmp_path / "options.json"
    payload = _options()
    payload.pop("poses")
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="poses"):
        load_dollimages_prompt_options(path)


def test_fantasy_options_use_a_dedicated_fantasy_catalog():
    template, options = load_dollimages_fantasy_prompt_options()

    assert "fantasy" in template
    assert "RAW photograph" in template
    assert "no illustration" in template
    assert "elven" in options["girl_types"][0]
    assert all("photograph" in style for style in options["styles"])
    assert not any(
        term in value.lower()
        for values in options.values()
        for value in values
        for term in ("illustration", "concept art", "3d render")
    )
    assert set(options) == set(_options())
