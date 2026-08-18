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
    assert set(_options()).issubset(options)
    assert all(len(values) >= 4 for values in options.values())


@pytest.mark.parametrize(
    "prompt_source",
    (
        "combinations",
        *(
            source
            for source in THEMED_OPTIONS_PATHS
            if source not in ("sauna_combinations", "oversized_tshirt_combinations")
        ),
    ),
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
    "prompt_source",
    (
        "combinations",
        *(
            source
            for source in THEMED_OPTIONS_PATHS
            if source
            not in (
                "bikini_combinations",
                "pool_combinations",
                "sauna_combinations",
                "oversized_tshirt_combinations",
            )
        ),
    ),
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


def test_bikini_catalog_uses_only_vivid_modern_micro_bikinis():
    template, options = load_dollimages_themed_prompt_options("bikini_combinations")
    outfits = options["outfits"]
    forbidden_terms = (
        "brown",
        "beige",
        "shirt",
        "shorts",
        "pants",
        "trousers",
        "skirt",
        "sarong",
        "wrap",
        "cover-up",
        "kimono",
        "lingerie",
        "bodysuit",
        "one-piece",
        "swimsuit",
    )
    vivid_colors = (
        "fuchsia",
        "cobalt",
        "neon",
        "coral",
        "turquoise",
        "pink",
        "tangerine",
        "violet",
        "cyan",
        "red",
        "yellow",
        "emerald",
        "aqua",
        "purple",
        "blue",
        "lime",
        "raspberry",
        "mint",
        "scarlet",
        "multicolor",
    )

    assert "wearing only [outfit]" in template
    assert all("micro bikini" in outfit.lower() for outfit in outfits)
    assert all(
        any(color in outfit.lower() for color in vivid_colors) for outfit in outfits
    )
    assert not any(
        term in outfit.lower() for outfit in outfits for term in forbidden_terms
    )


def test_bikini_catalog_fills_the_details_token():
    template, options = load_dollimages_themed_prompt_options("bikini_combinations")

    selection = choose_dollimages_prompt_selection(random.Random(7), options)
    prompt = fill_dollimages_prompt_tokens(template, selection)

    assert selection.details in options["details"]
    assert selection.details in prompt
    assert "[details]" not in prompt


def test_pool_catalog_has_only_micro_bikinis_without_shirts():
    template, options = load_dollimages_themed_prompt_options("pool_combinations")
    outfits = [outfit.lower() for outfit in options["outfits"]]

    assert "pool" in template.lower()
    assert all("micro bikini" in outfit for outfit in outfits)
    assert not any(
        term in outfit
        for outfit in outfits
        for term in (
            "shirt",
            "t-shirt",
            "swimsuit",
            "one-piece",
            "sarong",
            "pareo",
            "cover-up",
        )
    )


def test_pool_catalog_includes_twilight_lunar_eclipse_and_normal_scenes():
    _, options = load_dollimages_themed_prompt_options("pool_combinations")
    locations = " ".join(options["locations"]).lower()
    lighting = " ".join(options["lighting"]).lower()

    assert "total lunar eclipse" in locations
    assert "sun and moon" in locations
    assert "twilight" in lighting
    assert any(
        daytime in lighting for daytime in ("morning", "midday", "daylight")
    )


def test_oversized_tshirt_catalog_uses_only_shirts_without_bottoms():
    template, options = load_dollimages_themed_prompt_options(
        "oversized_tshirt_combinations"
    )
    outfits = [outfit.lower() for outfit in options["outfits"]]
    forbidden_bottoms = (
        "pants",
        "trousers",
        "shorts",
        "skirt",
        "dress",
        "leggings",
        "jeans",
    )

    assert "wearing only [outfit]" in template
    assert "no pants, no shorts, no skirt" in template
    assert all("oversized" in outfit and "shirt" in outfit for outfit in outfits)
    assert not any(term in outfit for outfit in outfits for term in forbidden_bottoms)
    assert any("sheer" in outfit or "translucent" in outfit for outfit in outfits)
    colors = ("white", "black", "pink", "red", "blue", "green", "orange", "purple")
    represented_colors = {
        color for outfit in outfits for color in colors if color in outfit
    }

    assert len(represented_colors) >= 6


def test_bikini_catalog_covers_reclining_and_seated_sand_scenes():
    _, options = load_dollimages_themed_prompt_options("bikini_combinations")
    poses = [pose.lower() for pose in options["poses"]]
    positions = ("lying face-up", "lying face-down", "reclining on her side", "sitting")
    beach_poses = [
        pose for pose in poses if pose.startswith(positions) and "sand" in pose
    ]

    for position in positions:
        variants = [pose for pose in beach_poses if pose.startswith(position)]

        assert len(variants) >= 4
        assert any("no towel or parasol" in pose for pose in variants)
        assert any("towel" in pose and "no parasol" in pose for pose in variants)
        assert any("parasol" in pose and "no towel" in pose for pose in variants)
        assert any("towel" in pose and "parasol" in pose for pose in variants)

    shots = " ".join(options["shots"]).lower()
    assert "reclining" in shots
    assert "overhead" in shots


@pytest.mark.parametrize(
    "prompt_source", ("travel_combinations", "summer_combinations")
)
def test_warm_weather_catalogs_use_current_colorful_fashion_and_dynamic_poses(
    prompt_source,
):
    _, options = load_dollimages_themed_prompt_options(prompt_source)
    outfits = " ".join(options["outfits"]).lower()
    poses = " ".join(options["poses"]).lower()
    shots = " ".join(options["shots"]).lower()

    assert sum("mini skirt" in outfit.lower() for outfit in options["outfits"]) >= 10
    assert "open" in outfits
    assert "fitted" in outfits
    assert "crop top" in outfits
    assert not any(term in outfits for term in ("leather", "silver", "golden"))
    assert sum("front" in pose.lower() for pose in options["poses"]) >= 4
    assert "jump" in poses
    assert "crouching" in poses
    assert "low-angle" in shots


def test_sauna_catalog_uses_only_towels_over_unclothed_bodies():
    template, options = load_dollimages_themed_prompt_options("sauna_combinations")

    assert "unclothed" in template.lower()
    assert "covered only" in template.lower()
    assert all("towel" in outfit.lower() for outfit in options["outfits"])
    assert all("bare body" in outfit.lower() for outfit in options["outfits"])
    assert not any(
        term in outfit.lower()
        for outfit in options["outfits"]
        for term in ("dress", "lingerie", "top", "shorts", "skirt", "bodysuit")
    )


def test_venice_carnival_catalog_uses_masks_and_venetian_locations():
    template, options = load_dollimages_themed_prompt_options(
        "venice_carnival_combinations"
    )

    locations = " ".join(options["locations"]).lower()

    assert "venice carnival" in template.lower()
    assert "venetian mask" in template.lower()
    assert all("mask" in outfit.lower() for outfit in options["outfits"])
    assert "saint mark's square" in locations
    assert "doge's palace" in locations
    assert "grand canal" in locations


def test_unknown_themed_catalog_is_rejected():
    with pytest.raises(ValueError, match="no es válido"):
        load_dollimages_themed_prompt_options("unknown_combinations")
