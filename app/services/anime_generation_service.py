from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime

from app.data.storage import get_store
from app.domain.models import AnimeGenerationCreate
from app.services.anime_v5_prompt_generator import (
    DEFAULT_TEMPLATE,
    choose_anime_v5_prompt_selection,
    fill_anime_v5_option_tokens,
    load_anime_v5_prompt_options,
)


@dataclass(frozen=True)
class AnimeCharacterRequest:
    name: str
    description: str = ""


def _default_character_description(character: str) -> str:
    return f"recognizable anime-inspired appearance of {character}"


def _parse_character_request(value: str) -> AnimeCharacterRequest | None:
    raw = str(value).strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            name = str(data.get("name") or "").strip()
            description = str(data.get("description") or "").strip()
            if name:
                return AnimeCharacterRequest(name=name, description=description)
    return AnimeCharacterRequest(name=raw)


@dataclass(frozen=True)
class AnimeGenerationResult:
    pack_id: int
    created_prompt_item_ids: list[int]
    created_queue_job_ids: list[int]


def _hash_signature(*values: object) -> str:
    return hashlib.sha1("|".join(str(v) for v in values).encode("utf-8")).hexdigest()


def _render_anime_prompt(
    prompt_template: str,
    *,
    character: str,
    list_name: str,
    description: str,
) -> str:
    character_description = description.strip() or _default_character_description(character)
    return (
        prompt_template.replace("[personaje]", character)
        .replace("[anime]", list_name)
        .replace("[description]", character_description)
        .replace("Dragon Ball", list_name)
    )


def _uses_anime_v5_generator(prompt_template: str) -> bool:
    return any(
        token in prompt_template
        for token in (
            "[shot]",
            "[pose]",
            "[location]",
            "[fit]",
            "[outfit]",
            "[fabric]",
            "[condition]",
            "[styling]",
            "[expression]",
            "[lighting]",
        )
    )


class AnimeGenerationService:
    def __init__(self) -> None:
        self.store = get_store()
        self.rng = random.Random()

    def create_images_and_enqueue(self, req: AnimeGenerationCreate) -> AnimeGenerationResult:
        list_name = req.list_name.strip()
        prompt_template = req.prompt_text.strip() or DEFAULT_TEMPLATE
        characters = [parsed for raw in req.characters if (parsed := _parse_character_request(raw)) is not None]
        if not list_name:
            raise ValueError("El nombre de la lista de personajes es obligatorio.")
        if not prompt_template:
            raise ValueError("El prompt es obligatorio.")
        if "[personaje]" not in prompt_template:
            raise ValueError("El prompt debe incluir el marcador [personaje].")
        if "[anime]" not in prompt_template and "Dragon Ball" not in prompt_template:
            raise ValueError("El prompt debe incluir el marcador [anime] o el texto Dragon Ball.")
        if not characters:
            raise ValueError("Añade al menos un personaje.")
        quantity = max(1, int(req.quantity_per_character))

        prompt_id = self.store.save_anime_prompt(
            prompt_id=None,
            title=req.prompt_title.strip() or list_name,
            prompt_text=prompt_template,
            enabled=True,
        )
        character_ids = [
            self.store.save_anime_character(
                character_id=None,
                list_name=list_name,
                name=character.name,
                description=character.description,
                enabled=True,
            )
            for character in characters
        ]

        requested = len(characters) * quantity
        pack_id = self.store.create_pack(
            category="anime",
            variant=list_name,
            requested_n=requested,
            notes=req.prompt_title.strip() or prompt_template,
        )

        created_prompt_item_ids: list[int] = []
        created_queue_job_ids: list[int] = []
        prompt_options = load_anime_v5_prompt_options() if _uses_anime_v5_generator(prompt_template) else None
        prompt_selection = (
            choose_anime_v5_prompt_selection(
                self.rng,
                prompt_options,
                fixed_outfit=req.fixed_outfit,
                manual_outfit_text=req.manual_outfit_text,
            )
            if prompt_options is not None
            else None
        )
        selected_template = (
            fill_anime_v5_option_tokens(prompt_template, prompt_selection)
            if prompt_selection is not None
            else prompt_template
        )
        created_at = datetime.now().isoformat(timespec="seconds")
        width, height = 1024, 1408

        for character_id, character in zip(character_ids, characters):
            character_description = character.description or _default_character_description(character.name)
            for repetition in range(quantity):
                rendered_prompt = _render_anime_prompt(
                    selected_template,
                    character=character.name,
                    list_name=list_name,
                    description=character_description,
                )
                signature = None
                seed = None
                for _ in range(10):
                    seed = self.rng.randint(0, 2**31 - 1)
                    candidate = _hash_signature("anime_v5", list_name, character.name, character_description, repetition, seed, prompt_template)
                    if self.store.try_register_combo(combo_key=candidate, category="anime", variant=list_name):
                        signature = candidate
                        break
                if signature is None or seed is None:
                    raise RuntimeError("No se pudo registrar una combinación única para Anime.")

                meta = {
                    "combo": {
                        "category": "anime",
                        "variant": list_name,
                        "ratio_tag": f"{width}x{height}",
                        "ratio": f"{width}x{height}",
                        "width": width,
                        "height": height,
                    },
                    "workflow": "anime_v5",
                    "seed": seed,
                    "width": width,
                    "height": height,
                    "anime_prompt_id": prompt_id,
                    "anime_character_id": character_id,
                    "anime_character": character.name,
                    "anime_character_description": character_description,
                    "anime_character_list": list_name,
                    "anime_prompt_template": prompt_template,
                    "anime_v5_prompt_selection": prompt_selection.as_meta() if prompt_selection else None,
                    "anime_v5_manual_outfit_text": req.manual_outfit_text.strip(),
                    "created_at": created_at,
                }
                if req.checkpoint_base or req.checkpoint_refiner:
                    meta["checkpoints"] = {
                        "base": req.checkpoint_base,
                        "refiner": req.checkpoint_refiner,
                    }

                item_id = self.store.create_prompt_item(
                    pack_id=pack_id,
                    title=f"{list_name} - {character.name}",
                    prompt_text=rendered_prompt,
                    negative_text="bad quality,worst quality,worst detail,sketch,censor, watermark, logo, text",
                    meta=meta,
                    signature=signature,
                    status="QUEUED",
                )
                created_prompt_item_ids.append(item_id)
                created_queue_job_ids.append(self.store.create_queue_job(prompt_item_id=item_id, priority=100))

        return AnimeGenerationResult(pack_id, created_prompt_item_ids, created_queue_job_ids)
