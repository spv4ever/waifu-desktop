from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List

from app.config.waifu_catalog import load_waifu_catalog
from app.services.waifu_prompt_builder import build_unique_prompts
from app.data.storage import get_store
from app.domain.models import PackCreate


@dataclass(frozen=True)
class PackCreateResult:
    pack_id: int
    created_prompt_item_ids: List[int]
    created_queue_job_ids: List[int]


class PackService:
    def __init__(self) -> None:
        self.store = get_store()
        self.catalog = load_waifu_catalog()

    def create_pack_and_enqueue(
        self,
        conn,
        req: PackCreate,
    ) -> PackCreateResult:
        """
        Crea un pack, genera prompts únicos desde el catálogo,
        guarda prompt_items y los encola.
        """

        # 1️⃣ Crear pack
        pack_id = self.store.create_pack(
            category=req.category,
            variant=req.variant,
            requested_n=req.requested_n,
            notes=req.notes or "",
        )

        created_prompt_item_ids: list[int] = []
        created_queue_job_ids: list[int] = []

        # 2️⃣ Generar prompts únicos (builder)
        self.catalog = load_waifu_catalog()
        built_prompts = build_unique_prompts(
            catalog=self.catalog,
            category_key=req.category,
            variant=req.variant,
            count=req.requested_n,
            combination_key=req.combination_key,
            nsfw_tag_count=req.nsfw_tag_count,
        )

        # 3️⃣ Insertar cada prompt (con control de unicidad global)
        for built in built_prompts:
            signature = built.signature

            # Registrar combinación (evita repetidos globales)
            ok = self.store.try_register_combo(
                combo_key=signature,
                category=req.category,
                variant=req.variant,
            )

            if not ok:
                # No debería pasar casi nunca, pero es seguro
                continue

            meta = dict(built.meta)
            if req.checkpoint_base or req.checkpoint_refiner:
                meta["checkpoints"] = {
                    "base": req.checkpoint_base,
                    "refiner": req.checkpoint_refiner,
                }

            prompt_item_id = self.store.create_prompt_item(
                pack_id=pack_id,
                title=built.title,
                prompt_text=built.prompt_text,
                negative_text=built.negative_text,
                meta=meta,
                signature=signature,
                status="QUEUED",
            )

            created_prompt_item_ids.append(prompt_item_id)

            # 4️⃣ Encolar job
            job_id = self.store.create_queue_job(prompt_item_id=prompt_item_id, priority=100)

            created_queue_job_ids.append(job_id)

        return PackCreateResult(
            pack_id=pack_id,
            created_prompt_item_ids=created_prompt_item_ids,
            created_queue_job_ids=created_queue_job_ids,
        )
