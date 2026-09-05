import pytest

from app.services.queue_worker import (
    _build_dollimages_output_folder,
    _build_dollimages_output_prefixes,
)


@pytest.mark.parametrize(
    ("prompt_source", "expected_folder"),
    [
        ("combinations", "dollimages/sfw/combinations"),
        ("fantasy_combinations", "dollimages/sfw/fantasy_combinations"),
        ("bikini_combinations", "dollimages/sfw/bikini_combinations"),
        ("lingerie_combinations", "dollimages/sfw/lingerie_combinations"),
        ("pool_combinations", "dollimages/sfw/pool_combinations"),
        ("river_combinations", "dollimages/sfw/river_combinations"),
        (
            "oversized_tshirt_combinations",
            "dollimages/sfw/oversized_tshirt_combinations",
        ),
        (
            "wet_tshirt_combinations",
            "dollimages/sfw/wet_tshirt_combinations",
        ),
        ("venice_carnival_combinations", "dollimages/sfw/venice_carnival_combinations"),
        (
            "andorra_travel_combinations",
            "dollimages/sfw/andorra_travel_combinations",
        ),
        ("ibiza_party_combinations", "dollimages/sfw/ibiza_party_combinations"),
    ],
)
def test_json_combinations_get_their_own_dollimages_folder(
    prompt_source, expected_folder
):
    folder = _build_dollimages_output_folder(
        meta={
            "dollimages_typology": "sfw",
            "dollimages_prompt_source": prompt_source,
        },
        combo={},
    )

    assert folder == expected_folder


def test_catalog_prompts_keep_the_existing_dollimages_folder():
    folder = _build_dollimages_output_folder(
        meta={
            "dollimages_typology": "nsfw",
            "dollimages_prompt_source": "catalog",
        },
        combo={},
    )

    assert folder == "dollimages/nsfw"


def test_combination_folder_segments_are_sanitized():
    folder = _build_dollimages_output_folder(
        meta={
            "dollimages_typology": "custom/type",
            "dollimages_prompt_source": "summer/combinations",
        },
        combo={},
    )

    assert folder == "dollimages/custom_type"


@pytest.mark.parametrize(
    "prompt_source",
    [
        "combinations",
        "fantasy_combinations",
        "summer_combinations",
        "bikini_combinations",
        "lingerie_combinations",
        "pool_combinations",
        "river_combinations",
        "oversized_tshirt_combinations",
        "wet_tshirt_combinations",
        "snow_combinations",
        "sauna_combinations",
        "travel_combinations",
        "andorra_travel_combinations",
        "venice_carnival_combinations",
        "ibiza_party_combinations",
    ],
)
def test_json_combinations_separate_base_and_upscale_outputs(prompt_source):
    base_prefix, upscale_prefix = _build_dollimages_output_prefixes(
        meta={
            "dollimages_typology": "sfw",
            "dollimages_prompt_source": prompt_source,
        },
        combo={},
        base_name="42_portrait",
    )

    assert base_prefix == f"dollimages/sfw/{prompt_source}/base/42_portrait"
    assert upscale_prefix == (
        f"dollimages/sfw/{prompt_source}/upscale/42_portrait"
    )


def test_catalog_outputs_keep_the_existing_shared_folder():
    base_prefix, upscale_prefix = _build_dollimages_output_prefixes(
        meta={
            "dollimages_typology": "nsfw",
            "dollimages_prompt_source": "catalog",
        },
        combo={},
        base_name="17_portrait",
    )

    assert base_prefix == "dollimages/nsfw/17_portrait"
    assert upscale_prefix == base_prefix
