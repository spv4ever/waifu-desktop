import pytest

from app.services.queue_worker import _build_dollimages_output_folder


@pytest.mark.parametrize(
    ("prompt_source", "expected_folder"),
    [
        ("combinations", "dollimages/sfw/combinations"),
        ("fantasy_combinations", "dollimages/sfw/fantasy_combinations"),
        ("bikini_combinations", "dollimages/sfw/bikini_combinations"),
        ("venice_carnival_combinations", "dollimages/sfw/venice_carnival_combinations"),
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
