import json
import random

import pytest

from app.services.dollimages_prompt_generator import (
    THEMED_OPTIONS_PATHS,
    choose_dollimages_prompt_selection,
    fill_dollimages_prompt_tokens,
    load_dollimages_prompt_options,
    load_dollimages_fantasy_prompt_options,
    load_dollimages_themed_prompt_options,
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


@pytest.mark.parametrize("prompt_source", THEMED_OPTIONS_PATHS)
def test_every_themed_catalog_is_complete_and_photographic(prompt_source):
    template, options = load_dollimages_themed_prompt_options(prompt_source)

    assert "photograph" in template.lower()
    assert set(options) == set(_options())
    assert all(len(values) >= 4 for values in options.values())


@pytest.mark.parametrize(
    "prompt_source", ("combinations", *THEMED_OPTIONS_PATHS)
)
def test_every_dollimages_outfit_is_sexy_and_avoids_conventional_suits(
    prompt_source,
):
    if prompt_source == "combinations":
        _, options = load_dollimages_prompt_options()
    else:
        _, options = load_dollimages_themed_prompt_options(prompt_source)

    sexy_outfit_terms = (
        "mini skirt",
        "micro ",
        "lingerie",
        "bralette",
        "bikini",
        "shorts",
        "deep neckline",
        "plunging neckline",
    )
    conventional_suit_terms = (
        " suit",
        "jumpsuit",
        "trousers",
        "pants",
        "blazer",
        "coat",
        "parka",
        "armor",
    )

    assert all(
        any(term in outfit.lower() for term in sexy_outfit_terms)
        for outfit in options["outfits"]
    )
    assert not any(
        term in outfit.lower()
        for outfit in options["outfits"]
        for term in conventional_suit_terms
    )


@pytest.mark.parametrize(
    "prompt_source", ("combinations", *THEMED_OPTIONS_PATHS)
)
def test_every_dollimages_catalog_includes_lingerie_bodysuits_and_sheer_outfits(
    prompt_source,
):
    if prompt_source == "combinations":
        _, options = load_dollimages_prompt_options()
    else:
        _, options = load_dollimages_themed_prompt_options(prompt_source)

    outfits = " ".join(options["outfits"]).lower()

    assert "lingerie" in outfits
    assert "bodysuit" in outfits
    assert "sheer" in outfits


def test_unknown_themed_catalog_is_rejected():
    with pytest.raises(ValueError, match="no es válido"):
        load_dollimages_themed_prompt_options("unknown_combinations")
