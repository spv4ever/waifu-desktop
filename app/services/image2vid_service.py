from __future__ import annotations

import hashlib
import random
from datetime import datetime
from dataclasses import dataclass

from app.data.storage import get_store
from app.domain.models import ImageToVideoCreate


@dataclass(frozen=True)
class ImageToVideoResult:
    pack_id: int
    created_prompt_item_ids: list[int]
    created_queue_job_ids: list[int]


def _hash_signature(*values: object) -> str:
    payload = "|".join(str(v) for v in values)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class ImageToVideoService:
    def __init__(self) -> None:
        self.store = get_store()

    def create_and_enqueue(self, req: ImageToVideoCreate) -> ImageToVideoResult:
        pack_id = self.store.create_pack(
            category="image2vid",
            variant=req.source_category,
            requested_n=1,
            notes=req.title or req.prompt_text or "image2vid",
        )

        rng = random.Random()
        signature = None
        seed = None
        for _ in range(15):
            seed = rng.randint(0, 2**31 - 1)
            candidate = _hash_signature(
                "image2vid",
                req.source_category,
                req.source_prompt_id,
                req.source_url,
                req.prompt_text,
                req.negative_text,
                req.ratio,
                req.width,
                req.height,
                req.length_frames,
                seed,
            )
            if self.store.try_register_combo(
                combo_key=candidate,
                category="image2vid",
                variant=req.source_category,
            ):
                signature = candidate
                break
        if signature is None or seed is None:
            raise RuntimeError("No se pudo registrar una combinación única para image2vid.")

        ratio_tag = f"{req.width}x{req.height}"
        created_at = datetime.now().isoformat(timespec="seconds")
        meta = {
            "combo": {
                "category": "image2vid",
                "variant": req.source_category,
                "ratio": req.ratio,
                "ratio_tag": ratio_tag,
                "width": req.width,
                "height": req.height,
            },
            "workflow": "image2vid",
            "seed": seed,
            "width": req.width,
            "height": req.height,
            "image2vid_source_category": req.source_category,
            "image2vid_source_prompt_id": req.source_prompt_id,
            "image2vid_source_url": req.source_url,
            "image2vid_ratio": req.ratio,
            "image2vid_seconds": req.seconds,
            "image2vid_fps": req.fps,
            "image2vid_length": req.length_frames,
            "created_at": created_at,
        }

        prompt_item_id = self.store.create_prompt_item(
            pack_id=pack_id,
            title=req.title,
            prompt_text=req.prompt_text,
            negative_text=req.negative_text,
            meta=meta,
            signature=signature,
            status="QUEUED",
        )
        job_id = self.store.create_queue_job(prompt_item_id=prompt_item_id, priority=100)

        return ImageToVideoResult(
            pack_id=pack_id,
            created_prompt_item_ids=[prompt_item_id],
            created_queue_job_ids=[job_id],
        )
