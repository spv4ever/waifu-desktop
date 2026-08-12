import json

from app.ui.data_source import _extract_category_variant


def test_extracts_explicit_dollimages_subcategory():
    meta = {
        "combo": {
            "category": "dollimages",
            "subcategory": "summer_combinations",
            "variant": "sfw",
        }
    }

    assert _extract_category_variant(json.dumps(meta)) == (
        "dollimages",
        "summer_combinations",
        "sfw",
    )


def test_old_dollimages_items_use_prompt_source_as_subcategory():
    meta = {
        "combo": {"category": "dollimages", "variant": "sfw"},
        "dollimages_prompt_source": "bikini_combinations",
    }

    assert _extract_category_variant(json.dumps(meta)) == (
        "dollimages",
        "bikini_combinations",
        "sfw",
    )
