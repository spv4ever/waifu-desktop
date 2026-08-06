from __future__ import annotations

import hashlib
import random
import shutil
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from app.config.app_config import load_app_config
from app.config.settings import settings
from app.data.storage import get_store
from app.domain.models import DollimagesPackCreate
from app.services.image_validation import validate_image_file
from app.services.path_utils import unique_suffixed_path
from app.services.dollimages_prompt_generator import (
    choose_dollimages_prompt_selection,
    fill_dollimages_prompt_tokens,
    load_dollimages_fantasy_prompt_options,
    load_dollimages_prompt_options,
)


COMBINATION_PROMPT_SOURCES = {"combinations", "fantasy_combinations"}


@dataclass(frozen=True)
class DollimagesPackCreateResult:
    pack_id: int
    created_prompt_item_ids: list[int]
    created_queue_job_ids: list[int]


def _append_manual_text(prompt_text: str, manual_text: str) -> str:
    base = prompt_text.strip()
    extra = manual_text.strip()
    if not extra:
        return base
    if not base:
        return extra
    return f"{base}, {extra}"


def _hash_signature(*values: object) -> str:
    payload = "|".join(str(v) for v in values)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class DollimagesPackService:
    def __init__(self) -> None:
        self.store = get_store()
        self.app_cfg = load_app_config()

    def _default_canvas(
        self, *, workflow_key: str = "dollimages", ratio: str = "3:4"
    ) -> tuple[int, int]:
        if workflow_key == "krea2":
            ratios = self.app_cfg.raw.get("krea2_ratios", {})
            if ratio in ratios:
                width, height = ratios[ratio]
                return int(width), int(height)
        defaults = self.app_cfg.raw.get("dollimages_defaults", {})
        width = int(defaults.get("width") or 832)
        height = int(defaults.get("height") or 1216)
        return width, height

    def _prepare_reference_image(self, reference_path: str) -> str:
        src = Path(reference_path)
        if not src.exists():
            raise FileNotFoundError(
                f"Imagen de referencia no encontrada: {reference_path}"
            )
        validate_image_file(src)
        input_dir = Path(settings.comfyui_input_dir)
        input_dir.mkdir(parents=True, exist_ok=True)
        target = input_dir / src.name
        if src.resolve() == target.resolve():
            return src.name
        target = unique_suffixed_path(target)
        shutil.copy2(src, target)
        return target.name

    def create_pack_and_enqueue(
        self,
        conn,
        req: DollimagesPackCreate,
    ) -> DollimagesPackCreateResult:
        if req.prompt_source not in {"catalog", *COMBINATION_PROMPT_SOURCES}:
            raise ValueError("El origen de prompts Dollimages no es válido.")
        faceswap_enabled = req.faceswap_enabled
        reference_image = req.reference_image
        checkpoint_base = req.checkpoint_base
        if req.workflow_key in {"dollimagesz", "krea2"}:
            faceswap_enabled = False
            reference_image = None
            checkpoint_base = None

        if faceswap_enabled and not reference_image:
            raise ValueError("La imagen de referencia es obligatoria.")

        catalog_prompts = (
            [
                row
                for row in self.store.list_dollimage_prompts(include_disabled=False)
                if row.typology == req.typology
                and (req.group_name is None or row.group_name == req.group_name)
            ]
            if req.prompt_source == "catalog"
            else []
        )
        if req.prompt_source in COMBINATION_PROMPT_SOURCES:
            loader = (
                load_dollimages_fantasy_prompt_options
                if req.prompt_source == "fantasy_combinations"
                else load_dollimages_prompt_options
            )
            template, options = loader()
            combination_count = max(1, int(req.combination_count))
        else:
            template, options, combination_count = "", {}, 0
        if req.prompt_source == "catalog" and not catalog_prompts:
            if req.group_name:
                raise ValueError(
                    f"No hay prompts para la tipología seleccionada en el grupo '{req.group_name}'."
                )
            raise ValueError("No hay prompts para la tipología seleccionada.")

        reference_name = ""
        if reference_image:
            reference_name = self._prepare_reference_image(reference_image)
        width, height = self._default_canvas(
            workflow_key=req.workflow_key, ratio=req.ratio
        )
        ratio_tag = req.ratio if req.workflow_key == "krea2" else f"{width}x{height}"

        requested_prompts = (
            combination_count
            if req.prompt_source in COMBINATION_PROMPT_SOURCES
            else len(catalog_prompts)
        )
        pack_id = self.store.create_pack(
            category="dollimages",
            variant=req.typology,
            requested_n=req.repetitions * requested_prompts,
            notes=req.manual_text or "",
        )

        created_prompt_item_ids: list[int] = []
        created_queue_job_ids: list[int] = []
        rng = random.Random()
        created_at = datetime.now().isoformat(timespec="seconds")

        generated_prompts = []
        if req.prompt_source in COMBINATION_PROMPT_SOURCES:
            for index in range(combination_count):
                selection = choose_dollimages_prompt_selection(rng, options)
                generated_prompts.append(
                    (
                        f"Combinación {index + 1}: {selection.girl_type}",
                        fill_dollimages_prompt_tokens(template, selection),
                        f"combination-{index + 1}",
                        selection.as_meta(),
                    )
                )
        else:
            generated_prompts = [
                (prompt.title, prompt.prompt_text, str(prompt.id), None)
                for prompt in catalog_prompts
            ]

        for (
            prompt_title,
            base_prompt_text,
            prompt_id,
            selection_meta,
        ) in generated_prompts:
            for repetition in range(req.repetitions):
                signature = None
                seed = None
                for _ in range(10):
                    seed = rng.randint(0, 2**31 - 1)
                    candidate = _hash_signature(
                        prompt_id,
                        req.typology,
                        req.workflow_key,
                        req.ratio,
                        repetition,
                        seed,
                        reference_name,
                        req.manual_text,
                    )
                    if self.store.try_register_combo(
                        combo_key=candidate,
                        category="dollimages",
                        variant=req.typology,
                    ):
                        signature = candidate
                        break
                if signature is None or seed is None:
                    raise RuntimeError(
                        "No se pudo registrar una combinación única para Dollimages."
                    )

                meta = {
                    "combo": {
                        "category": "dollimages",
                        "variant": req.typology,
                        "ratio_tag": ratio_tag,
                        "ratio": ratio_tag,
                        "width": width,
                        "height": height,
                    },
                    "workflow": req.workflow_key,
                    "seed": seed,
                    "width": width,
                    "height": height,
                    "reference_image": reference_name,
                    "faceswap_enabled": faceswap_enabled,
                    "dollimages_prompt_id": prompt_id,
                    "dollimages_typology": req.typology,
                    "dollimages_group": req.group_name or "",
                    "created_at": created_at,
                    "dollimages_prompt_source": req.prompt_source,
                    "dollimages_prompt_selection": selection_meta,
                }

                if checkpoint_base:
                    meta["checkpoints"] = {
                        "base": checkpoint_base,
                        "refiner": checkpoint_base,
                    }

                prompt_text = _append_manual_text(base_prompt_text, req.manual_text)

                prompt_item_id = self.store.create_prompt_item(
                    pack_id=pack_id,
                    title=prompt_title,
                    prompt_text=prompt_text,
                    negative_text="",
                    meta=meta,
                    signature=signature,
                    status="QUEUED",
                )

                created_prompt_item_ids.append(prompt_item_id)
                job_id = self.store.create_queue_job(
                    prompt_item_id=prompt_item_id, priority=100
                )
                created_queue_job_ids.append(job_id)

        return DollimagesPackCreateResult(
            pack_id=pack_id,
            created_prompt_item_ids=created_prompt_item_ids,
            created_queue_job_ids=created_queue_job_ids,
        )
