from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import List

from app.config.waifu_catalog import load_waifu_catalog
from app.services.waifu_prompt_builder import build_unique_prompts
from app.data.repositories import (
    PackRepository,
    PromptItemRepository,
    QueueRepository,
    ComboRegistryRepository,
)
from app.domain.models import PackCreate


@dataclass(frozen=True)
class PackCreateResult:
    pack_id: int
    created_prompt_item_ids: List[int]
    created_queue_job_ids: List[int]


class PackService:
    def __init__(self) -> None:
        self.pack_repo = PackRepository()
        self.item_repo = PromptItemRepository()
        self.queue_repo = QueueRepository()
        self.combo_registry = ComboRegistryRepository()
        self.catalog = load_waifu_catalog()

    def create_pack_and_enqueue(
        self,
        conn: sqlite3.Connection,
        req: PackCreate,
    ) -> PackCreateResult:
        """
        Crea un pack, genera prompts únicos desde el catálogo,
        guarda prompt_items y los encola.
        """

        # 1️⃣ Crear pack
        pack_id = self.pack_repo.create(
            conn,
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
        )

        # 3️⃣ Insertar cada prompt (con control de unicidad global)
        for built in built_prompts:
            signature = built.signature

            # Registrar combinación (evita repetidos globales)
            ok = self.combo_registry.try_register(
                conn,
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

            prompt_item_id = self.item_repo.create(
                conn,
                pack_id=pack_id,
                title=built.title,
                prompt_text=built.prompt_text,
                negative_text=built.negative_text,
                meta=meta,
                signature=signature,
                status="CREATED",
            )

            created_prompt_item_ids.append(prompt_item_id)

            # 4️⃣ Encolar job
            job_id = self.queue_repo.enqueue(
                conn,
                prompt_item_id=prompt_item_id,
                priority=100,
            )

            created_queue_job_ids.append(job_id)

        return PackCreateResult(
            pack_id=pack_id,
            created_prompt_item_ids=created_prompt_item_ids,
            created_queue_job_ids=created_queue_job_ids,
        )
