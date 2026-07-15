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
from app.domain.models import DollimagesManualPromptCreate
from app.services.image_validation import validate_image_file
from app.services.path_utils import unique_suffixed_path


@dataclass(frozen=True)
class DollimagesManualPromptResult:
    pack_id: int
    created_prompt_item_ids: list[int]
    created_queue_job_ids: list[int]


def _hash_signature(*values: object) -> str:
    payload = "|".join(str(v) for v in values)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class DollimagesManualPromptService:
    def __init__(self) -> None:
        self.store = get_store()
        self.app_cfg = load_app_config()

    def _default_canvas(self, *, workflow_key: str = "dollimages", ratio: str = "3:4") -> tuple[int, int]:
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
            raise FileNotFoundError(f"Imagen de referencia no encontrada: {reference_path}")
        validate_image_file(src)
        input_dir = Path(settings.comfyui_input_dir)
        input_dir.mkdir(parents=True, exist_ok=True)
        target = input_dir / src.name
        if src.resolve() == target.resolve():
            return src.name
        target = unique_suffixed_path(target)
        shutil.copy2(src, target)
        return target.name

    def create_manual_prompts_and_enqueue(
        self,
        req: DollimagesManualPromptCreate,
    ) -> DollimagesManualPromptResult:
        faceswap_enabled = req.faceswap_enabled
        reference_image = req.reference_image
        checkpoint_base = req.checkpoint_base
        if req.workflow_key in {"dollimagesz", "krea2"}:
            faceswap_enabled = False
            reference_image = None
            checkpoint_base = None

        if faceswap_enabled and not reference_image:
            raise ValueError("La imagen de referencia es obligatoria.")

        reference_name = ""
        if reference_image:
            reference_name = self._prepare_reference_image(reference_image)
        width, height = self._default_canvas(workflow_key=req.workflow_key, ratio=req.ratio)
        ratio_tag = req.ratio if req.workflow_key == "krea2" else f"{width}x{height}"

        pack_id = self.store.create_pack(
            category="dollimages",
            variant=req.typology,
            requested_n=req.repetitions,
            notes=req.prompt_text or "",
        )

        created_prompt_item_ids: list[int] = []
        created_queue_job_ids: list[int] = []
        rng = random.Random()
        created_at = datetime.now().isoformat(timespec="seconds")

        for repetition in range(req.repetitions):
            signature = None
            seed = None
            for _ in range(10):
                seed = rng.randint(0, 2**31 - 1)
                candidate = _hash_signature(
                    req.typology,
                    req.workflow_key,
                    req.ratio,
                    repetition,
                    seed,
                    reference_name,
                    req.prompt_text,
                    req.title,
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
                "dollimages_prompt_id": None,
                "dollimages_typology": req.typology,
                "dollimages_group": "",
                "dollimages_manual": True,
                "created_at": created_at,
            }

            if checkpoint_base:
                meta["checkpoints"] = {
                    "base": checkpoint_base,
                    "refiner": checkpoint_base,
                }

            prompt_item_id = self.store.create_prompt_item(
                pack_id=pack_id,
                title=req.title,
                prompt_text=req.prompt_text,
                negative_text="",
                meta=meta,
                signature=signature,
                status="QUEUED",
            )

            created_prompt_item_ids.append(prompt_item_id)
            job_id = self.store.create_queue_job(prompt_item_id=prompt_item_id, priority=100)
            created_queue_job_ids.append(job_id)

        return DollimagesManualPromptResult(
            pack_id=pack_id,
            created_prompt_item_ids=created_prompt_item_ids,
            created_queue_job_ids=created_queue_job_ids,
        )
