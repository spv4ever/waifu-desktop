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

    def _default_canvas(self) -> tuple[int, int]:
        defaults = self.app_cfg.raw.get("dollimages_defaults", {})
        width = int(defaults.get("width") or 832)
        height = int(defaults.get("height") or 1216)
        return width, height

    def _prepare_reference_image(self, reference_path: str) -> str:
        src = Path(reference_path)
        if not src.exists():
            raise FileNotFoundError(f"Imagen de referencia no encontrada: {reference_path}")
        validate_image_file(src)
        input_dir = Path(settings.comfyui_input_dir)
        input_dir.mkdir(parents=True, exist_ok=True)
        target = input_dir / src.name
        if src.resolve() == target.resolve():
            return src.name
        if target.exists():
            stem = src.stem
            suffix = src.suffix
            counter = 1
            while True:
                candidate = input_dir / f"{stem}_{counter}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
                counter += 1
        shutil.copy2(src, target)
        return target.name

    def create_pack_and_enqueue(
        self,
        conn,
        req: DollimagesPackCreate,
    ) -> DollimagesPackCreateResult:
        faceswap_enabled = req.faceswap_enabled
        reference_image = req.reference_image
        checkpoint_base = req.checkpoint_base
        if req.workflow_key == "dollimagesz":
            faceswap_enabled = False
            reference_image = None
            checkpoint_base = None

        if faceswap_enabled and not reference_image:
            raise ValueError("La imagen de referencia es obligatoria.")

        prompts = [
            row
            for row in self.store.list_dollimage_prompts(include_disabled=False)
            if row.typology == req.typology
            and (req.group_name is None or row.group_name == req.group_name)
        ]
        if not prompts:
            if req.group_name:
                raise ValueError(
                    f"No hay prompts para la tipología seleccionada en el grupo '{req.group_name}'."
                )
            raise ValueError("No hay prompts para la tipología seleccionada.")

        reference_name = ""
        if reference_image:
            reference_name = self._prepare_reference_image(reference_image)
        width, height = self._default_canvas()
        ratio_tag = f"{width}x{height}"

        pack_id = self.store.create_pack(
            category="dollimages",
            variant=req.typology,
            requested_n=req.repetitions * len(prompts),
            notes=req.manual_text or "",
        )

        created_prompt_item_ids: list[int] = []
        created_queue_job_ids: list[int] = []
        rng = random.Random()
        created_at = datetime.now().isoformat(timespec="seconds")

        for prompt in prompts:
            for repetition in range(req.repetitions):
                signature = None
                seed = None
                for _ in range(10):
                    seed = rng.randint(0, 2**31 - 1)
                    candidate = _hash_signature(
                        prompt.id,
                        req.typology,
                        req.workflow_key,
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
                    raise RuntimeError("No se pudo registrar una combinación única para Dollimages.")

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
                    "dollimages_prompt_id": prompt.id,
                    "dollimages_typology": req.typology,
                    "dollimages_group": req.group_name or "",
                    "created_at": created_at,
                }

                if checkpoint_base:
                    meta["checkpoints"] = {
                        "base": checkpoint_base,
                        "refiner": checkpoint_base,
                    }

                prompt_text = _append_manual_text(prompt.prompt_text, req.manual_text)

                prompt_item_id = self.store.create_prompt_item(
                    pack_id=pack_id,
                    title=prompt.title,
                    prompt_text=prompt_text,
                    negative_text="",
                    meta=meta,
                    signature=signature,
                    status="QUEUED",
                )

                created_prompt_item_ids.append(prompt_item_id)
                job_id = self.store.create_queue_job(prompt_item_id=prompt_item_id, priority=100)
                created_queue_job_ids.append(job_id)

        return DollimagesPackCreateResult(
            pack_id=pack_id,
            created_prompt_item_ids=created_prompt_item_ids,
            created_queue_job_ids=created_queue_job_ids,
        )
