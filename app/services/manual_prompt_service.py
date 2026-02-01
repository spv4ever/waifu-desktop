from __future__ import annotations

import random

from app.config.app_config import load_app_config
from app.data.storage import get_store
from app.domain.models import CreatedPack, ManualPromptCreate
from app.services.combo_key import make_combo_key
from app.services.ratios import resolve_size


class ManualPromptService:
    def __init__(self) -> None:
        self.store = get_store()
        self.app_config = load_app_config()

    def create_manual_prompts_and_enqueue(self, req: ManualPromptCreate) -> CreatedPack:
        defaults = self.app_config.defaults
        ratios = self.app_config.ratios

        width, height = resolve_size(
            ratios,
            req.ratio,
            fallback_w=int(defaults.get("width", 1024)),
            fallback_h=int(defaults.get("height", 1024)),
        )

        pack_id = self.store.create_pack(
            category=req.category,
            variant=req.variant,
            requested_n=req.quantity,
            notes=req.notes or "manual_prompt",
        )

        created_prompt_item_ids: list[int] = []
        created_queue_job_ids: list[int] = []
        rng = random.Random()
        attempts = 0
        max_attempts = max(req.quantity * 5, req.quantity + 3)

        while len(created_prompt_item_ids) < req.quantity and attempts < max_attempts:
            seed = rng.randint(0, 2**31 - 1)
            signature = make_combo_key(
                {
                    "category": req.category,
                    "variant": req.variant,
                    "ratio": req.ratio,
                    "seed": seed,
                    "title": req.title,
                    "prompt_text": req.prompt_text,
                }
            )
            attempts += 1

            if not self.store.try_register_combo(
                combo_key=signature,
                category=req.category,
                variant=req.variant,
            ):
                continue

            combo = {
                "category": req.category,
                "variant": req.variant,
                "ratio": req.ratio,
                "ratio_tag": req.ratio,
                "width": width,
                "height": height,
            }
            meta = {
                "combo": combo,
                "seed": seed,
                "width": width,
                "height": height,
                "ratio": req.ratio,
            }
            if req.checkpoint_base:
                meta["checkpoints"] = {
                    "base": req.checkpoint_base,
                    "refiner": req.checkpoint_base,
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

        if len(created_prompt_item_ids) < req.quantity:
            raise RuntimeError(
                "No se pudieron generar todos los prompts manuales solicitados. "
                f"Solicitados={req.quantity}, creados={len(created_prompt_item_ids)}."
            )

        return CreatedPack(
            pack_id=pack_id,
            created_prompt_item_ids=created_prompt_item_ids,
            created_queue_job_ids=created_queue_job_ids,
        )
