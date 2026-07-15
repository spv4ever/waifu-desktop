from __future__ import annotations

import random
from dataclasses import dataclass

from app.config.app_config import load_app_config
from app.config.bulk_images_prompts import BulkImagePrompt
from app.data.storage import get_store
from app.domain.models import CreatedPack
from app.services.combo_key import make_combo_key
from app.services.ratios import resolve_size


_BULK_WORKFLOW_HINTS = {
    "bulk_images_default": "krea2",
    "dollimages": "dollimages",
    "dollimagesz": "dollimagesz",
    "krea2": "krea2",
    "waifu": "waifu",
}


def _resolve_bulk_workflow_key(workflow_hint: str) -> str:
    return _BULK_WORKFLOW_HINTS.get(workflow_hint.strip().lower(), "krea2")


def _looks_like_checkpoint(value: str) -> bool:
    return value.lower().endswith((".safetensors", ".ckpt", ".pt", ".pth"))


@dataclass(frozen=True)
class BulkImagesEnqueueRequest:
    prompts: list[BulkImagePrompt]
    checkpoint_base: str | None = None


class BulkImagesService:
    def __init__(self) -> None:
        self.store = get_store()
        self.app_config = load_app_config()

    def create_prompts_and_enqueue(self, req: BulkImagesEnqueueRequest) -> CreatedPack:
        prompts = [prompt for prompt in req.prompts if prompt.enabled and prompt.positive_prompt.strip()]
        if not prompts:
            raise ValueError("No hay prompts activos con prompt positivo para enviar a la cola.")

        defaults = self.app_config.defaults
        ratios = self.app_config.ratios
        category = "bulk_images"
        variant = "library"
        pack_id = self.store.create_pack(
            category=category,
            variant=variant,
            requested_n=len(prompts),
            notes="bulk_images_prompt_library",
        )

        created_prompt_item_ids: list[int] = []
        created_queue_job_ids: list[int] = []
        rng = random.Random()

        for prompt in prompts:
            width, height = resolve_size(
                ratios,
                prompt.ratio,
                fallback_w=int(defaults.get("width", 1024)),
                fallback_h=int(defaults.get("height", 1024)),
            )
            seed = rng.randint(0, 2**31 - 1)
            signature = make_combo_key(
                {
                    "source": "bulk_images",
                    "bulk_prompt_id": prompt.id,
                    "title": prompt.title,
                    "prompt_text": prompt.positive_prompt,
                    "negative_text": prompt.negative_prompt,
                    "ratio": prompt.ratio,
                    "seed": seed,
                }
            )
            if not self.store.try_register_combo(combo_key=signature, category=category, variant=variant):
                continue

            workflow_key = _resolve_bulk_workflow_key(prompt.workflow_hint)
            meta = {
                "source": "bulk_images",
                "workflow": workflow_key,
                "bulk_prompt_id": prompt.id,
                "bulk_metadata": {
                    "category": prompt.category,
                    "subcategory": prompt.subcategory,
                    "collection": prompt.collection,
                    "subject": prompt.subject,
                    "style": prompt.style,
                    "mood": prompt.mood,
                    "environment": prompt.environment,
                    "lighting": prompt.lighting,
                    "camera": prompt.camera,
                    "composition": prompt.composition,
                    "color_palette": prompt.color_palette,
                    "model_hint": prompt.model_hint,
                    "workflow_hint": prompt.workflow_hint,
                    "tags": prompt.tags,
                    "priority": prompt.priority,
                    "status": prompt.status,
                },
                "combo": {
                    "category": category,
                    "variant": variant,
                    "ratio": prompt.ratio,
                    "ratio_tag": prompt.ratio,
                    "width": width,
                    "height": height,
                },
                "seed": seed,
                "width": width,
                "height": height,
                "ratio": prompt.ratio,
            }
            checkpoint = req.checkpoint_base or (prompt.model_hint if _looks_like_checkpoint(prompt.model_hint) else None)
            if checkpoint and workflow_key in {"dollimages", "waifu"}:
                meta["checkpoints"] = {"base": checkpoint, "refiner": checkpoint}

            prompt_item_id = self.store.create_prompt_item(
                pack_id=pack_id,
                title=prompt.title or prompt.id,
                prompt_text=prompt.positive_prompt,
                negative_text=prompt.negative_prompt,
                meta=meta,
                signature=signature,
                status="QUEUED",
            )
            created_prompt_item_ids.append(prompt_item_id)
            created_queue_job_ids.append(self.store.create_queue_job(prompt_item_id=prompt_item_id, priority=prompt.priority))

        if len(created_prompt_item_ids) != len(prompts):
            raise RuntimeError(
                "No se pudieron registrar todos los prompts Bulk Images. "
                f"Solicitados={len(prompts)}, creados={len(created_prompt_item_ids)}."
            )

        return CreatedPack(
            pack_id=pack_id,
            created_prompt_item_ids=created_prompt_item_ids,
            created_queue_job_ids=created_queue_job_ids,
        )
