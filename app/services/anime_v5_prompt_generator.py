from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_OPTIONS_PATH = Path("resources/config/anime_v5_prompt_options.json")
REQUIRED_GROUPS = ("locations", "poses", "outfits", "expressions", "lighting", "shots")
DEFAULT_TEMPLATE = (
    "Adult [personaje] from [anime], single female character, [shot], [pose], [location], "
    "wearing [outfit], [expression], [lighting], fashion editorial photography, cinematic composition, "
    "centered composition, single subject, SFW, ultra realistic, photorealistic, masterpiece, HDR, "
    "volumetric lighting, depth of field, ultra detailed, sharp focus, realistic anatomy, symmetrical face, "
    "detailed eyes, 8k."
)

TOKEN_BY_GROUP = {
    "locations": "[location]",
    "poses": "[pose]",
    "outfits": "[outfit]",
    "expressions": "[expression]",
    "lighting": "[lighting]",
    "shots": "[shot]",
}


@dataclass(frozen=True)
class AnimeV5PromptSelection:
    location: str
    pose: str
    outfit: str
    expression: str
    lighting: str
    shot: str

    def as_meta(self) -> dict[str, str]:
        return {
            "location": self.location,
            "pose": self.pose,
            "outfit": self.outfit,
            "expression": self.expression,
            "lighting": self.lighting,
            "shot": self.shot,
        }


def load_anime_v5_prompt_options(path: Path | None = None) -> dict[str, list[str]]:
    config_path = path or DEFAULT_OPTIONS_PATH
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError("La configuración de prompts Anime V5 debe ser un objeto JSON.")
    options: dict[str, list[str]] = {}
    for group in REQUIRED_GROUPS:
        values = raw.get(group)
        if not isinstance(values, list):
            raise ValueError(f"La opción Anime V5 '{group}' debe ser una lista.")
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned:
            raise ValueError(f"La opción Anime V5 '{group}' debe incluir al menos un valor.")
        options[group] = cleaned
    return options


def choose_anime_v5_prompt_selection(
    rng: random.Random,
    options: Mapping[str, list[str]] | None = None,
) -> AnimeV5PromptSelection:
    data = dict(options) if options is not None else load_anime_v5_prompt_options()
    return AnimeV5PromptSelection(
        location=rng.choice(data["locations"]),
        pose=rng.choice(data["poses"]),
        outfit=rng.choice(data["outfits"]),
        expression=rng.choice(data["expressions"]),
        lighting=rng.choice(data["lighting"]),
        shot=rng.choice(data["shots"]),
    )


def fill_anime_v5_option_tokens(prompt_template: str, selection: AnimeV5PromptSelection) -> str:
    replacements = {
        "[location]": selection.location,
        "[pose]": selection.pose,
        "[outfit]": selection.outfit,
        "[expression]": selection.expression,
        "[lighting]": selection.lighting,
        "[shot]": selection.shot,
    }
    rendered = prompt_template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    return rendered
