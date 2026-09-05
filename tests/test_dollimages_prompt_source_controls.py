import pytest

from app.services.dollimages_pack_service import COMBINATION_PROMPT_SOURCES
from app.services.dollimages_pack_service import is_combination_prompt_source


def test_venice_carnival_is_a_combination_prompt_source():
    assert "venice_carnival_combinations" in COMBINATION_PROMPT_SOURCES
    assert is_combination_prompt_source("venice_carnival_combinations")


def test_ibiza_party_is_a_combination_prompt_source():
    assert "ibiza_party_combinations" in COMBINATION_PROMPT_SOURCES
    assert is_combination_prompt_source("ibiza_party_combinations")


def test_river_is_a_combination_prompt_source():
    assert "river_combinations" in COMBINATION_PROMPT_SOURCES
    assert is_combination_prompt_source("river_combinations")


def test_wet_tshirt_is_a_combination_prompt_source():
    assert "wet_tshirt_combinations" in COMBINATION_PROMPT_SOURCES
    assert is_combination_prompt_source("wet_tshirt_combinations")


def test_andorra_travel_is_a_combination_prompt_source():
    assert "andorra_travel_combinations" in COMBINATION_PROMPT_SOURCES
    assert is_combination_prompt_source("andorra_travel_combinations")


@pytest.mark.parametrize("prompt_source", sorted(COMBINATION_PROMPT_SOURCES))
def test_every_json_prompt_source_enables_editing_combination_count(prompt_source):
    assert is_combination_prompt_source(prompt_source) is True


def test_fixed_catalog_disables_editing_combination_count():
    assert is_combination_prompt_source("catalog") is False
