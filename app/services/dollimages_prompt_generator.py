from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_OPTIONS_PATH = Path("resources/config/dollimages_prompt_options.json")
FANTASY_OPTIONS_PATH = Path("resources/config/dollimages_fantasy_prompt_options.json")
THEMED_OPTIONS_PATHS = {
    "fantasy_combinations": FANTASY_OPTIONS_PATH,
    "summer_combinations": Path(
        "resources/config/dollimages_summer_prompt_options.json"
    ),
    "bikini_combinations": Path(
        "resources/config/dollimages_bikini_prompt_options.json"
    ),
    "snow_combinations": Path("resources/config/dollimages_snow_prompt_options.json"),
    "sauna_combinations": Path("resources/config/dollimages_sauna_prompt_options.json"),
    "travel_combinations": Path(
        "resources/config/dollimages_travel_prompt_options.json"
    ),
}
REQUIRED_GROUPS = (
    "girl_types",
    "poses",
    "outfits",
    "locations",
    "expressions",
    "lighting",
    "shots",
    "styles",
)
DEFAULT_TEMPLATE = (
    "[girl_type], single female subject, [shot], [pose], wearing [outfit], [location], "
    "[expression], [lighting], [style], cinematic composition, photorealistic, highly detailed, "
    "realistic anatomy, detailed eyes, sharp focus."
)


@dataclass(frozen=True)
class DollimagesPromptSelection:
    girl_type: str
    pose: str
    outfit: str
    location: str
    expression: str
    lighting: str
    shot: str
    style: str

    def as_meta(self) -> dict[str, str]:
        return dict(self.__dict__)


def load_dollimages_prompt_options(
    path: Path | None = None,
) -> tuple[str, dict[str, list[str]]]:
    config_path = path or DEFAULT_OPTIONS_PATH
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError(
            "La configuración combinatoria de Dollimages debe ser un objeto JSON."
        )
    template = str(raw.get("template") or DEFAULT_TEMPLATE).strip()
    options: dict[str, list[str]] = {}
    for group in REQUIRED_GROUPS:
        values = raw.get(group)
        if not isinstance(values, list):
            raise ValueError(f"La opción Dollimages '{group}' debe ser una lista.")
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned:
            raise ValueError(
                f"La opción Dollimages '{group}' debe incluir al menos un valor."
            )
        options[group] = cleaned
    return template, options


def load_dollimages_fantasy_prompt_options() -> tuple[str, dict[str, list[str]]]:
    """Load the dedicated fantasy combinations catalog."""
    return load_dollimages_prompt_options(FANTASY_OPTIONS_PATH)


def load_dollimages_themed_prompt_options(
    prompt_source: str,
) -> tuple[str, dict[str, list[str]]]:
    """Load a dedicated combination catalog by its UI/source identifier."""
    try:
        path = THEMED_OPTIONS_PATHS[prompt_source]
    except KeyError as exc:
        raise ValueError(f"El tema Dollimages '{prompt_source}' no es válido.") from exc
    return load_dollimages_prompt_options(path)


def choose_dollimages_prompt_selection(
    rng: random.Random, options: Mapping[str, list[str]]
) -> DollimagesPromptSelection:
    return DollimagesPromptSelection(
        girl_type=rng.choice(options["girl_types"]),
        pose=rng.choice(options["poses"]),
        outfit=rng.choice(options["outfits"]),
        location=rng.choice(options["locations"]),
        expression=rng.choice(options["expressions"]),
        lighting=rng.choice(options["lighting"]),
        shot=rng.choice(options["shots"]),
        style=rng.choice(options["styles"]),
    )


def fill_dollimages_prompt_tokens(
    template: str, selection: DollimagesPromptSelection
) -> str:
    rendered = template
    for name, value in selection.as_meta().items():
        rendered = rendered.replace(f"[{name}]", value)
    return rendered
