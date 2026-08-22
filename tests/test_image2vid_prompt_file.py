import pytest

from app.services.image2vid_prompt_file import parse_image2vid_long_prompts


def test_parses_saved_long_project_prompts_and_ignores_seed() -> None:
    text = """Seed: 566882835

Prompt 1:
First movement
continues here

Prompt 2:
Second movement
"""

    assert parse_image2vid_long_prompts(text) == [
        "First movement\ncontinues here",
        "Second movement",
    ]


def test_parses_prompts_in_numeric_order() -> None:
    assert parse_image2vid_long_prompts("Prompt 2: second\nPrompt 1: first") == [
        "first",
        "second",
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Seed: 123", "formato 'Prompt 1:'"),
        ("Prompt 1:\n", "Prompt 1 está vacío"),
        ("Prompt 1: one\nPrompt 1: again", "más de una vez"),
    ],
)
def test_rejects_invalid_prompt_files(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_image2vid_long_prompts(text)
