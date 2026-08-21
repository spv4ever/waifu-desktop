from __future__ import annotations

import hashlib
import random
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import settings
from app.data.storage import get_store
from app.domain.models import ImageToVideoCreate
from app.services.image_validation import validate_image_file
from app.services.path_utils import unique_suffixed_path


try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - dependency guard for minimal environments
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]


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

    def _prepare_source_image(self, source_path: str) -> str:
        src = Path(source_path)
        if not src.exists():
            raise FileNotFoundError(f"Imagen de referencia no encontrada: {source_path}")
        validate_image_file(src)

        input_dir = Path(settings.comfyui_input_dir)
        input_dir.mkdir(parents=True, exist_ok=True)

        if Image is None or ImageOps is None:
            target = input_dir / src.name
            if src.resolve() == target.resolve():
                return src.name
            target = unique_suffixed_path(target)
            target.write_bytes(src.read_bytes())
            return target.name

        target = unique_suffixed_path(input_dir / f"{src.stem}_image2vid.png")
        try:
            with Image.open(src) as image:
                normalized = ImageOps.exif_transpose(image)
                if normalized.mode not in {"RGB", "RGBA"}:
                    normalized = normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB")
                normalized.save(target, format="PNG")
        except (OSError, ValueError) as exc:
            raise ValueError(f"No se pudo preparar la imagen para Image2Vid: {src.name}") from exc

        validate_image_file(target)
        return target.name

    def create_and_enqueue(
        self, req: ImageToVideoCreate, *, workflow_key: str = "image2vid"
    ) -> ImageToVideoResult:
        return self.create_many_and_enqueue([req], workflow_key=workflow_key)

    def create_many_and_enqueue(
        self, requests: list[ImageToVideoCreate], *, workflow_key: str = "image2vid"
    ) -> ImageToVideoResult:
        if workflow_key not in {"image2vid", "undress"}:
            raise ValueError(f"Workflow de vídeo no soportado: {workflow_key}")
        if not requests:
            raise ValueError("Debes indicar al menos un prompt para Image2Vid.")
        first = requests[0]
        pack_id = self.store.create_pack(
            category=workflow_key,
            variant=first.source_category,
            requested_n=len(requests),
            notes=first.title or first.prompt_text or "image2vid",
        )

        source_image = self._prepare_source_image(first.source_image)
        prompt_item_ids: list[int] = []
        queue_job_ids: list[int] = []
        for req in requests:
            prompt_item_id, job_id = self._enqueue_request(
                req, pack_id=pack_id, source_image=source_image, workflow_key=workflow_key
            )
            prompt_item_ids.append(prompt_item_id)
            queue_job_ids.append(job_id)

        return ImageToVideoResult(
            pack_id=pack_id,
            created_prompt_item_ids=prompt_item_ids,
            created_queue_job_ids=queue_job_ids,
        )

    def create_long_and_enqueue(
        self, requests: list[ImageToVideoCreate], *, seed: int | None = None
    ) -> ImageToVideoResult:
        """Create one ordered project whose clips continue from the prior last frame."""
        if not requests:
            raise ValueError("Debes indicar al menos un prompt para Image2Vid Long.")
        if any(abs(req.seconds - 5.0) > 0.001 for req in requests):
            raise ValueError("Cada tramo de Image2Vid Long debe durar exactamente 5 segundos.")

        first = requests[0]
        if seed is None:
            seed = random.randint(0, 2**31 - 1)
        if not 0 <= seed <= 2**31 - 1:
            raise ValueError("El seed de Image2Vid Long debe estar entre 0 y 2147483647.")
        pack_id = self.store.create_pack(
            category="image2vid_long",
            variant=first.source_category,
            requested_n=len(requests),
            notes=first.title or "Image2Vid Long",
        )
        source_image = self._prepare_source_image(first.source_image)
        prompt_ids: list[int] = []
        job_ids: list[int] = []
        previous_prompt_id: int | None = None
        for index, req in enumerate(requests):
            prompt_id, job_id = self._enqueue_request(
                req,
                pack_id=pack_id,
                source_image=source_image,
                workflow_key="image2vid",
                extra_meta={
                    "image2vid_long": True,
                    "image2vid_long_project_id": pack_id,
                    "image2vid_long_initial_source_image": source_image,
                    "image2vid_long_index": index,
                    "image2vid_long_count": len(requests),
                    "image2vid_long_previous_prompt_id": previous_prompt_id,
                    "image2vid_long_final": index == len(requests) - 1,
                    "image2vid_long_seed": seed,
                },
                seed=seed,
            )
            prompt_ids.append(prompt_id)
            job_ids.append(job_id)
            previous_prompt_id = prompt_id
        self.store.update_prompt_item_meta(
            prompt_id=prompt_ids[-1],
            updates={"image2vid_long_prompt_ids": prompt_ids},
        )
        return ImageToVideoResult(pack_id, prompt_ids, job_ids)

    def _enqueue_request(
        self,
        req: ImageToVideoCreate,
        *,
        pack_id: int,
        source_image: str,
        workflow_key: str,
        extra_meta: dict[str, object] | None = None,
        seed: int | None = None,
    ) -> tuple[int, int]:
        rng = random.Random()
        signature = None
        fixed_seed = seed is not None
        for _ in range(1 if fixed_seed else 15):
            if not fixed_seed:
                seed = rng.randint(0, 2**31 - 1)
            candidate = _hash_signature(
                workflow_key,
                req.source_category,
                req.source_prompt_id,
                req.source_image,
                req.prompt_text,
                req.negative_text,
                req.ratio,
                req.width,
                req.height,
                req.length_frames,
                seed,
                pack_id if fixed_seed else "",
                (extra_meta or {}).get("image2vid_long_index", "") if fixed_seed else "",
            )
            if self.store.try_register_combo(
                combo_key=candidate,
                category=workflow_key,
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
                "category": workflow_key,
                "variant": req.source_category,
                "ratio": req.ratio,
                "ratio_tag": ratio_tag,
                "width": req.width,
                "height": req.height,
            },
            "workflow": workflow_key,
            "seed": seed,
            "width": req.width,
            "height": req.height,
            "image2vid_source_category": req.source_category,
            "image2vid_source_prompt_id": req.source_prompt_id,
            "image2vid_source_url": req.source_url,
            "image2vid_source_image": source_image,
            "image2vid_ratio": req.ratio,
            "image2vid_seconds": req.seconds,
            "image2vid_fps": req.fps,
            "image2vid_length": req.length_frames,
            "created_at": created_at,
        }
        if extra_meta:
            meta.update(extra_meta)

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

        return prompt_item_id, job_id
