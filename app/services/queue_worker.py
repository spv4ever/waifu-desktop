from __future__ import annotations

import json
import random
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Literal, Any, Callable

import requests

from app.data.storage import get_store
from app.config.settings import settings
from app.services.comfy_client import ComfyClient
from app.services.cloudinary_uploader import (
    CloudinaryUploadError,
    upload_dollimages_image,
    upload_dollimages_video,
    upload_anime_image,
    upload_waifu_image,
    upload_waifu_video,
)
from app.services.image_validation import validate_image_file
from app.services.output_paths import build_output_path
from app.services.workflow_service import WorkflowService
from app.config.app_config import load_app_config
from app.utils.path_sanitize import sanitize_segment, sanitize_relpath
from app.services.comfy_history_parser import (
    extract_base_and_upscale,
    extract_base_and_upscale_images,
    extract_video_output,
    has_rendered_media,
)


WorkerResult = Literal["PROCESSED", "PAUSED", "EMPTY"]


def _select_dollimages_upload_images(
    *,
    base_images: list[dict[str, Any]],
    up_images: list[dict[str, Any]],
    base_img: dict[str, Any] | None,
    up_img: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Prioriza todas las imágenes upscale y conserva el lote completo."""
    selected_images = up_images or base_images
    if selected_images:
        return selected_images
    fallback_image = up_img or base_img
    return [fallback_image] if fallback_image else []


class QueueWorker:
    def __init__(self, *, log_callback: Callable[[str], None] | None = None) -> None:
        self.store = get_store()
        self.comfy = ComfyClient()
        self.dollimages_comfy = (
            ComfyClient(base_url=settings.comfyui_dollimages_base_url)
            if settings.comfyui_dollimages_base_url
            else None
        )
        self.workflow = WorkflowService()
        self.app_cfg = load_app_config()
        self._log_callback = log_callback
        self._progress_callback: Callable[[], None] | None = None
        self._stop_requested = False

    def set_progress_callback(self, callback: Callable[[], None] | None) -> None:
        self._progress_callback = callback

    def request_stop(self) -> None:
        self._stop_requested = True

    def _should_stop(self) -> bool:
        return self._stop_requested

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)

    def _emit_progress(self) -> None:
        if self._progress_callback:
            self._progress_callback()

    def _upload_dollimages_to_cloudinary(
        self,
        *,
        prompt_item_id: int,
        meta: dict[str, Any],
        checkpoint_base: str | None,
        image_json: dict[str, Any] | None = None,
        image_jsons: list[dict[str, Any]] | None = None,
        title: str,
    ) -> None:
        images = image_jsons if image_jsons is not None else ([image_json] if image_json else [])
        images = [image for image in images if image]
        if not images:
            self._log(f"[WORKER] Dollimages sin imagen para subir prompt_item_id={prompt_item_id}")
            return

        uploaded_images = meta.get("cloudinary_images")
        if isinstance(uploaded_images, list) and len(uploaded_images) >= len(images):
            return
        if meta.get("cloudinary_url") and len(images) == 1:
            return

        created_at = str(meta.get("created_at") or "").strip()
        if not created_at:
            created_at = datetime.now().isoformat(timespec="seconds")

        workflow_key = str(meta.get("workflow") or "dollimages")
        successful_uploads: list[dict[str, Any]] = []
        for index, current_image_json in enumerate(images, start=1):
            try:
                image_path = build_output_path(current_image_json, workflow_key=workflow_key)
                payload = upload_dollimages_image(
                    image_path=image_path,
                    title=f"{title or 'Dollimages'} #{index}" if len(images) > 1 else title or "Dollimages",
                    checkpoint=checkpoint_base,
                    version=settings.dollimages_version or None,
                    created_at=created_at,
                )
            except (CloudinaryUploadError, OSError, ValueError) as exc:
                self._log(
                    f"[WORKER] Cloudinary error prompt_item_id={prompt_item_id} "
                    f"imagen={index}/{len(images)}: {exc}"
                )
                continue

            successful_uploads.append(
                {
                    "url": payload.get("secure_url") or payload.get("url"),
                    "public_id": payload.get("public_id"),
                    "image_json": current_image_json,
                }
            )

        if not successful_uploads:
            return

        first_upload = successful_uploads[0]
        updates = {
            "cloudinary_url": first_upload.get("url"),
            "cloudinary_public_id": first_upload.get("public_id"),
            "cloudinary_uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "cloudinary_images": successful_uploads,
        }
        self.store.update_prompt_item_meta(prompt_id=prompt_item_id, updates=updates)

    def _upload_waifu_to_cloudinary(
        self,
        *,
        prompt_item_id: int,
        meta: dict[str, Any],
        checkpoint_base: str | None,
        image_json: dict[str, Any] | None = None,
        image_jsons: list[dict[str, Any]] | None = None,
        title: str,
    ) -> None:
        images = image_jsons if image_jsons is not None else ([image_json] if image_json else [])
        images = [image for image in images if image]
        if not images:
            self._log(f"[WORKER] Waifu sin imagen para subir prompt_item_id={prompt_item_id}")
            return

        uploaded_images = meta.get("waifu_cloudinary_images")
        if isinstance(uploaded_images, list) and len(uploaded_images) >= len(images):
            return
        if meta.get("waifu_cloudinary_url") and len(images) == 1:
            return

        created_at = str(meta.get("created_at") or "").strip()
        if not created_at:
            created_at = datetime.now().isoformat(timespec="seconds")

        successful_uploads: list[dict[str, Any]] = []
        for index, current_image_json in enumerate(images, start=1):
            try:
                image_path = build_output_path(current_image_json, workflow_key="waifu")
                payload = upload_waifu_image(
                    image_path=image_path,
                    title=f"{title or 'Waifu'} #{index}" if len(images) > 1 else title or "Waifu",
                    checkpoint=checkpoint_base,
                    version=settings.waifu_version or None,
                    created_at=created_at,
                )
            except (CloudinaryUploadError, OSError, ValueError) as exc:
                self._log(
                    f"[WORKER] Cloudinary error prompt_item_id={prompt_item_id} "
                    f"imagen={index}/{len(images)}: {exc}"
                )
                continue

            successful_uploads.append(
                {
                    "url": payload.get("secure_url") or payload.get("url"),
                    "public_id": payload.get("public_id"),
                    "image_json": current_image_json,
                }
            )

        if not successful_uploads:
            return

        first_upload = successful_uploads[0]
        updates = {
            "waifu_cloudinary_url": first_upload.get("url"),
            "waifu_cloudinary_public_id": first_upload.get("public_id"),
            "waifu_cloudinary_uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "waifu_cloudinary_images": successful_uploads,
        }
        self.store.update_prompt_item_meta(prompt_id=prompt_item_id, updates=updates)


    def _upload_anime_to_cloudinary(
        self,
        *,
        prompt_item_id: int,
        meta: dict[str, Any],
        checkpoint_base: str | None,
        image_json: dict[str, Any] | None = None,
        image_jsons: list[dict[str, Any]] | None = None,
        title: str,
    ) -> None:
        images = image_jsons if image_jsons is not None else ([image_json] if image_json else [])
        images = [image for image in images if image]
        if not images:
            self._log(f"[WORKER] Anime sin imagen para subir prompt_item_id={prompt_item_id}")
            return

        uploaded_images = meta.get("anime_cloudinary_images")
        if isinstance(uploaded_images, list) and len(uploaded_images) >= len(images):
            return
        if meta.get("anime_cloudinary_url") and len(images) == 1:
            return

        created_at = str(meta.get("created_at") or "").strip() or datetime.now().isoformat(timespec="seconds")
        content_rating = str(meta.get("anime_v5_content_rating") or "sfw").strip().lower()
        if content_rating not in {"sfw", "nsfw"}:
            content_rating = "sfw"
        version_base = str(settings.waifu_version or "anime").strip() or "anime"
        upload_version = f"{version_base} {content_rating}"
        successful_uploads: list[dict[str, Any]] = []
        for index, current_image_json in enumerate(images, start=1):
            try:
                image_path = build_output_path(current_image_json, workflow_key="anime_v5")
                payload = upload_anime_image(
                    image_path=image_path,
                    title=f"{title or 'Anime'} #{index}" if len(images) > 1 else title or "Anime",
                    checkpoint=checkpoint_base,
                    version=upload_version,
                    created_at=created_at,
                )
            except (CloudinaryUploadError, OSError, ValueError) as exc:
                self._log(
                    f"[WORKER] Cloudinary anime error prompt_item_id={prompt_item_id} "
                    f"imagen={index}/{len(images)}: {exc}"
                )
                continue

            successful_uploads.append(
                {
                    "url": payload.get("secure_url") or payload.get("url"),
                    "public_id": payload.get("public_id"),
                    "image_json": current_image_json,
                }
            )

        if not successful_uploads:
            return

        first_upload = successful_uploads[0]
        self.store.update_prompt_item_meta(
            prompt_id=prompt_item_id,
            updates={
                "anime_cloudinary_url": first_upload.get("url"),
                "anime_cloudinary_public_id": first_upload.get("public_id"),
                "anime_cloudinary_uploaded_at": datetime.now().isoformat(timespec="seconds"),
                "anime_cloudinary_images": successful_uploads,
            },
        )

    def _upload_image2vid_to_cloudinary(
        self,
        *,
        prompt_item_id: int,
        meta: dict[str, Any],
        video_json: dict[str, Any] | None,
        title: str,
    ) -> None:
        if not video_json:
            self._log(f"[WORKER] Image2Vid sin video para subir prompt_item_id={prompt_item_id}")
            return
        if meta.get("image2vid_cloudinary_url"):
            return
        created_at = str(meta.get("created_at") or "").strip()
        if not created_at:
            created_at = datetime.now().isoformat(timespec="seconds")
        source_category = str(meta.get("image2vid_source_category") or "waifu").strip().lower()

        try:
            video_path = build_output_path(video_json, workflow_key="image2vid")
            video_path = self._add_reel_music_to_image2vid(video_path=video_path)
            if source_category == "dollimages":
                payload = upload_dollimages_video(
                    video_path=video_path,
                    title=title or "Dollimages Image2Vid",
                    created_at=created_at,
                )
            else:
                payload = upload_waifu_video(
                    video_path=video_path,
                    title=title or "Waifu Image2Vid",
                    created_at=created_at,
                )
        except (CloudinaryUploadError, OSError, ValueError) as exc:
            self._log(f"[WORKER] Cloudinary video error prompt_item_id={prompt_item_id}: {exc}")
            return

        updates = {
            "image2vid_cloudinary_url": payload.get("secure_url") or payload.get("url"),
            "image2vid_cloudinary_public_id": payload.get("public_id"),
            "image2vid_cloudinary_uploaded_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.store.update_prompt_item_meta(prompt_id=prompt_item_id, updates=updates)

    def _pick_reel_audio_for_duration(self, *, duration_seconds: float) -> tuple[Path, float, bool] | None:
        repo_root = Path(__file__).resolve().parents[2]
        audio_dir = repo_root / "resources" / "audio"
        if not audio_dir.exists():
            return None

        audio_files = sorted(audio_dir.glob("*.mp3"))
        if not audio_files:
            return None

        audio_path = random.choice(audio_files)
        ffprobe_path = shutil.which("ffprobe")
        start_time = 0.0
        loop_audio = False

        if ffprobe_path:
            try:
                probe = subprocess.run(
                    [
                        ffprobe_path,
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(audio_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                audio_duration = float(probe.stdout.strip())
                if audio_duration > duration_seconds:
                    start_time = random.uniform(0.0, max(audio_duration - duration_seconds, 0.0))
                else:
                    loop_audio = True
            except (ValueError, subprocess.CalledProcessError):
                loop_audio = True
        else:
            loop_audio = True

        return audio_path, start_time, loop_audio

    def _probe_video_duration(self, *, video_path: Path) -> float | None:
        ffprobe_path = shutil.which("ffprobe")
        if not ffprobe_path:
            return None
        try:
            probe = subprocess.run(
                [
                    ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return float(probe.stdout.strip())
        except (ValueError, subprocess.CalledProcessError):
            return None

    def _add_reel_music_to_image2vid(self, *, video_path: Path) -> Path:
        if not video_path.exists():
            return video_path

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            self._log("[WORKER] ffmpeg no disponible; se sube image2vid sin música.")
            return video_path

        duration_seconds = self._probe_video_duration(video_path=video_path)
        if not duration_seconds or duration_seconds <= 0:
            self._log("[WORKER] No se pudo medir duración de image2vid; se sube sin música.")
            return video_path

        audio_selection = self._pick_reel_audio_for_duration(duration_seconds=duration_seconds)
        if not audio_selection:
            return video_path

        audio_path, start_time, loop_audio = audio_selection
        output_path = video_path.with_name(f"{video_path.stem}_music{video_path.suffix}")

        cmd = [ffmpeg_path, "-y", "-i", str(video_path)]
        if loop_audio:
            cmd += ["-stream_loop", "-1"]
        cmd += [
            "-ss",
            f"{start_time}",
            "-t",
            f"{duration_seconds}",
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            self._log(f"[WORKER] No se pudo añadir música a image2vid: {exc}")
            return video_path

        self._log(f"[WORKER] Image2Vid con música aplicada: {audio_path.name}")
        return output_path

    def recover_inflight_jobs(self, conn=None) -> tuple[int, int, int]:
        return self.store.recover_inflight_jobs()

    def _is_finished(self, history: dict[str, Any], prompt_id: str) -> tuple[bool, dict[str, Any] | None]:
        entry = history.get(prompt_id)
        if not entry:
            return False, None
        return has_rendered_media(entry), entry

    def _extract_progress(self, entry: dict[str, Any]) -> int | None:
        status = entry.get("status")
        if not isinstance(status, dict):
            return None

        completed = status.get("completed")
        total = status.get("total")
        if isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
            return int(min(100, max(0, (completed / total) * 100)))

        raw_progress = status.get("progress")
        if isinstance(raw_progress, (int, float)):
            if raw_progress <= 1:
                return int(min(100, max(0, raw_progress * 100)))
            return int(min(100, max(0, raw_progress)))

        value = status.get("value")
        maximum = status.get("max")
        if isinstance(value, (int, float)) and isinstance(maximum, (int, float)) and maximum > 0:
            return int(min(100, max(0, (value / maximum) * 100)))

        return None

    def _extract_backend_status(self, entry: dict[str, Any]) -> str | None:
        status = entry.get("status")
        if not isinstance(status, dict):
            return None

        parts: list[str] = []
        node = status.get("current_node") or status.get("node") or status.get("node_name")
        if isinstance(node, str) and node.strip():
            parts.append(node.strip())

        message = status.get("message")
        if isinstance(message, str) and message.strip():
            parts.append(message.strip())

        status_str = status.get("status_str")
        if isinstance(status_str, str) and status_str.strip() and status_str.strip() not in parts:
            parts.append(status_str.strip())

        if not parts:
            return None

        return " · ".join(parts)

    def _requeue_for_retry(self, conn, *, job_id: int, prompt_item_id: int, reason: str) -> None:
        self._log(f"[WORKER] Reencolando job_id={job_id} ({reason})")
        self.store.reset_for_retry(job_id)
        self.store.bulk_update_prompt_status(ids=[prompt_item_id], status="QUEUED")
        self._emit_progress()

    def _parse_comfy_error(self, error: Exception) -> tuple[str | None, dict[str, Any] | None]:
        message = str(error)
        prefix = "ComfyUI /prompt error"
        if prefix not in message:
            return None, None
        _, _, remainder = message.partition(": ")
        remainder = remainder.strip()
        if not remainder:
            return message, None
        try:
            payload = json.loads(remainder)
        except json.JSONDecodeError:
            return message, None
        error_block = payload.get("error")
        if isinstance(error_block, dict):
            error_type = error_block.get("type")
            if isinstance(error_type, str):
                return error_type, payload
        return message, payload

    def _should_mark_failed(self, error: Exception) -> tuple[bool, str]:
        error_type, payload = self._parse_comfy_error(error)
        message = str(error)
        if error_type == "prompt_outputs_failed_validation":
            details = ""
            if isinstance(payload, dict):
                node_errors = payload.get("node_errors")
                if isinstance(node_errors, dict):
                    details = json.dumps(node_errors, ensure_ascii=False)
            reason = "ComfyUI rechazó el prompt por validación"
            if details:
                reason = f"{reason}: {details}"
            return True, reason
        if "Invalid image file" in message or "Formato de imagen no válido" in message:
            return True, message
        return False, message

    def process_one(self, conn=None, *, delay_seconds: float = 0.2) -> WorkerResult:
        if self._should_stop():
            self._log("[WORKER] Stop solicitado. No se procesarán más jobs.")
            return "EMPTY"

        paused = self.store.kv_get("queue_paused", "false")
        if paused == "true":
            return "PAUSED"

        job = self.store.fetch_next_pending()
        if not job:
            return "EMPTY"

        job_id = int(job.id)
        prompt_item_id = int(job.prompt_item_id)

        item = self.store.get_prompt_item(prompt_item_id)
        if not item:
            self.store.mark_failed(job_id, f"prompt_item_id={prompt_item_id} no existe")
            return "PROCESSED"

        meta = json.loads(item["meta_json"]) if item.get("meta_json") else {}
        combo = meta.get("combo", {})
        checkpoints = meta.get("checkpoints", {}) if isinstance(meta.get("checkpoints"), dict) else {}
        checkpoint_base = checkpoints.get("base")
        checkpoint_refiner = checkpoints.get("refiner")
        workflow_key = str(meta.get("workflow") or "waifu")
        use_dollimages_comfy = workflow_key in {"dollimages", "dollimagesz", "anime_v5"}
        if workflow_key == "image2vid":
            use_dollimages_comfy = True
        comfy_client = self.dollimages_comfy if use_dollimages_comfy and self.dollimages_comfy else self.comfy

        reference_image = None
        mapping_key = "comfyui_workflow"
        faceswap_enabled = meta.get("faceswap_enabled")

        if workflow_key in {"dollimages", "dollimagesz"}:
            typology = sanitize_segment(
                meta.get("dollimages_typology") or combo.get("variant") or "normal"
            )
            folder = sanitize_relpath(f"dollimages/{typology}")
            reference_image = meta.get("reference_image")
            if reference_image:
                input_path = Path(settings.comfyui_input_dir) / reference_image
                try:
                    validate_image_file(input_path)
                except ValueError as exc:
                    self.store.mark_failed(job_id, str(exc))
                    return "PROCESSED"
            reference_stem = sanitize_segment(Path(reference_image).stem) if reference_image else ""
            title_segment = sanitize_segment(item.get("title") or "")
            if reference_stem:
                base_name = f"{reference_stem}_{prompt_item_id}"
            else:
                base_name = f"{prompt_item_id}" if not title_segment else f"{prompt_item_id}_{title_segment}"
            base_prefix = sanitize_relpath(f"{folder}/{base_name}")
            upscale_prefix = base_prefix
            width = int(meta.get("width") or 832)
            height = int(meta.get("height") or 1216)
            seed = meta.get("seed")
            mapping_key = (
                "comfyui_workflow_dollimagesz"
                if workflow_key == "dollimagesz"
                else "comfyui_workflow_dollimages"
            )
        elif workflow_key == "anime_v5":
            content_rating = str(meta.get("anime_v5_content_rating") or "sfw").strip().lower()
            list_name = sanitize_segment(meta.get("anime_character_list") or combo.get("variant") or "characters")
            character = sanitize_segment(meta.get("anime_character") or item.get("title") or prompt_item_id)
            folder_prefix = "anime/nsfw" if content_rating == "nsfw" else "anime"
            folder = sanitize_relpath(f"{folder_prefix}/{list_name}/{character}")
            base_name = sanitize_segment(f"{prompt_item_id}")
            base_prefix = sanitize_relpath(f"{folder}/{base_name}")
            upscale_prefix = base_prefix
            width = int(meta.get("width") or combo.get("width") or 1024)
            height = int(meta.get("height") or combo.get("height") or 1408)
            seed = meta.get("seed")
            mapping_key = "comfyui_workflow_anime_v5"
        elif workflow_key == "image2vid":
            source_category = str(meta.get("image2vid_source_category") or "waifu").strip().lower()
            folder = sanitize_relpath(f"image2vid/{'dollimages' if source_category == 'dollimages' else 'waifu'}")
            base_name = sanitize_segment(f"{prompt_item_id}")
            base_prefix = sanitize_relpath(f"{folder}/{base_name}")
            upscale_prefix = base_prefix
            width = int(meta.get("width") or 480)
            height = int(meta.get("height") or 720)
            seed = meta.get("seed")
            reference_image = str(
                meta.get("image2vid_source_image") or meta.get("image2vid_source_url") or ""
            ).strip()
            if reference_image and not reference_image.startswith(("http://", "https://")):
                input_path = Path(settings.comfyui_input_dir) / reference_image
                try:
                    validate_image_file(input_path)
                except ValueError as exc:
                    self.store.mark_failed(job_id, str(exc))
                    return "PROCESSED"
            mapping_key = "comfyui_workflow_image2vid"
        else:
            # -------------------------
            # PATH / NAMING (Jerarquía correcta)
            # anime/Waifu/<category>/<variant>/<ratio>_<id>[_4k]
            # -------------------------
            category = sanitize_segment(combo.get("category", "cat"))
            variant = sanitize_segment(combo.get("variant", "v01"))
            ratio = sanitize_segment(combo.get("ratio_tag") or combo.get("ratio") or "1x1")

            folder = sanitize_relpath(f"anime/Waifu/{category}/{variant}")

            base_name = sanitize_segment(f"{ratio}_{prompt_item_id}")
            base_prefix = sanitize_relpath(f"{folder}/{base_name}")
            upscale_prefix = sanitize_relpath(f"{folder}/{base_name}_4k")

            # Tamaños (ratio -> width/height ya vienen en meta/combo)
            width = int(meta.get("width") or combo.get("width") or 1024)
            height = int(meta.get("height") or combo.get("height") or 1024)

            # Seed opcional
            seed = meta.get("seed")

        # Opción 1: steps bloqueados (NO tocar steps en workflow)
        defaults = self.app_cfg.raw.get("defaults", {})
        lock_steps = bool(defaults.get("lock_steps", False))

        # Si NO está bloqueado, entonces sí usamos steps (pero en tu caso lock_steps=true)
        steps = None
        if not lock_steps:
            steps = int(meta.get("steps") or combo.get("steps") or int(defaults.get("steps", 50)))

        # 1) SUBMIT si no tiene remote_id
        remote_id = job.remote_id
        submitted_now = False
        if not remote_id:
            wf = self.workflow.load_template(workflow_key=workflow_key)

            wf = self.workflow.apply_overrides(
                wf,
                prompt_text=item["prompt_text"],
                negative_text=item.get("negative_text") or "",
                seed=seed,
                steps=steps,  # None si lock_steps=true -> workflow_service NO debe tocar steps
                width=width,
                height=height,
                filename_prefix_base=base_prefix,
                filename_prefix_upscale=upscale_prefix,
                checkpoint_base=checkpoint_base,
                checkpoint_refiner=checkpoint_refiner,
                load_image=reference_image,
                faceswap_enabled=faceswap_enabled,
                mapping_key=mapping_key,
            )

            if workflow_key == "image2vid":
                image2vid_length = int(meta.get("image2vid_length") or 81)
                node_98 = wf.get("98") if isinstance(wf, dict) else None
                if isinstance(node_98, dict):
                    inputs = node_98.get("inputs")
                    if isinstance(inputs, dict):
                        inputs["length"] = image2vid_length

            try:
                remote_id = comfy_client.submit_prompt(wf)
            except (requests.RequestException, RuntimeError) as exc:
                mark_failed, reason = self._should_mark_failed(exc)
                if mark_failed:
                    self.store.mark_failed(job_id, reason)
                    self.store.bulk_update_prompt_status(ids=[prompt_item_id], status="FAILED")
                    self._emit_progress()
                    return "PROCESSED"
                self._requeue_for_retry(
                    conn,
                    job_id=job_id,
                    prompt_item_id=prompt_item_id,
                    reason=f"error enviando prompt ({exc})",
                )
                return "PROCESSED"
            submitted_now = True
            self.store.set_remote(job_id, remote_id, "SUBMITTED")
            self._log(f"[WORKER] SUBMITTED job_id={job_id} remote_id={remote_id}")

        # 2) POLL hasta terminar (sin saturar, 1 en vuelo)
        poll = float(settings.comfyui_poll_interval)
        last_progress: int | None = None
        last_backend_status: str | None = None
        last_logged_status: str | None = None
        missing_history_started: float | None = None
        max_missing_seconds = float(settings.comfyui_history_wait_seconds)
        while True:
            if self._should_stop():
                self._log("[WORKER] Stop solicitado durante polling.")
                return "PROCESSED"
            paused = self.store.kv_get("queue_paused", "false")
            if paused == "true":
                self._log("[WORKER] Pausado durante polling. Se reanudará más tarde.")
                self.store.set_remote_status(job_id, "PAUSED_WAITING")
                return "PROCESSED"

            try:
                history = comfy_client.get_history(remote_id)
            except requests.RequestException as exc:
                self._requeue_for_retry(
                    conn,
                    job_id=job_id,
                    prompt_item_id=prompt_item_id,
                    reason=f"error consultando history ({exc})",
                )
                return "PROCESSED"

            if not history or remote_id not in history:
                if missing_history_started is None:
                    missing_history_started = time.monotonic()
                    self.store.set_remote_status(job_id, "WAITING_HISTORY")
                    self._emit_progress()

                elapsed = time.monotonic() - missing_history_started
                if elapsed >= max_missing_seconds:
                    still_queued = False
                    queue_lookup_error: str | None = None
                    try:
                        still_queued = comfy_client.is_prompt_in_queue(remote_id)
                    except requests.RequestException as exc:
                        queue_lookup_error = str(exc)

                    if still_queued:
                        self.store.set_remote_status(job_id, "WAITING_QUEUE")
                        self._log(
                            f"[WORKER] job_id={job_id} remote_id={remote_id} sigue en cola remota sin history; esperando"
                        )
                        missing_history_started = time.monotonic()
                        self._emit_progress()
                        time.sleep(poll)
                        continue

                    if queue_lookup_error:
                        self._log(
                            f"[WORKER] No se pudo verificar /queue para job_id={job_id}: {queue_lookup_error}. "
                            "Se mantiene en espera de history."
                        )
                        missing_history_started = time.monotonic()
                        self.store.set_remote_status(job_id, "WAITING_HISTORY")
                        self._emit_progress()
                        time.sleep(poll)
                        continue

                    self._requeue_for_retry(
                        conn,
                        job_id=job_id,
                        prompt_item_id=prompt_item_id,
                        reason="history sin entrada para remote_id y no aparece en /queue",
                    )
                    return "PROCESSED"
                time.sleep(poll)
                continue
            missing_history_started = None

            finished, entry = self._is_finished(history, remote_id)

            if entry:
                progress = self._extract_progress(entry)
                if progress is not None and progress != last_progress:
                    last_progress = progress
                    self.store.set_progress(job_id, progress)
                    mode = "IMAGE2VID" if workflow_key == "image2vid" else "RENDER"
                    self._log(
                        f"[WORKER][{mode}] job_id={job_id} remote_id={remote_id} progreso={progress}%"
                    )
                    self._emit_progress()

                backend_status = self._extract_backend_status(entry)
                if backend_status and backend_status != last_backend_status:
                    last_backend_status = backend_status
                    self.store.set_backend_status(job_id, backend_status)
                    if backend_status != last_logged_status:
                        mode = "IMAGE2VID" if workflow_key == "image2vid" else "RENDER"
                        self._log(
                            f"[WORKER][{mode}] job_id={job_id} remote_id={remote_id} estado={backend_status}"
                        )
                        last_logged_status = backend_status
                    self._emit_progress()

            if finished and entry:
                base_images, up_images = extract_base_and_upscale_images(entry, workflow_key=workflow_key)
                base_img = base_images[0] if base_images else None
                up_img = up_images[0] if up_images else None
                if not base_img and not up_img:
                    base_img, up_img = extract_base_and_upscale(entry, workflow_key=workflow_key)

                self.store.set_remote_status(job_id, "COMPLETED")
                self.store.set_output_json(job_id, json.dumps(entry, ensure_ascii=False))
                self.store.set_progress(job_id, 100)
                self.store.set_backend_status(job_id, "Completado")
                self._emit_progress()

                video_output = extract_video_output(entry) if workflow_key == "image2vid" else None

                # Guardar outputs en prompt_item
                self.store.set_prompt_outputs(
                    item_id=prompt_item_id,
                    base_image_json=json.dumps(base_img, ensure_ascii=False) if base_img and workflow_key != "image2vid" else None,
                    upscale_image_json=json.dumps(up_img, ensure_ascii=False) if up_img and workflow_key != "image2vid" else None,
                )

                self.store.mark_done(job_id)
                self.store.bulk_update_prompt_status(ids=[prompt_item_id], status="DONE")

                if workflow_key == "image2vid":
                    self._upload_image2vid_to_cloudinary(
                        prompt_item_id=prompt_item_id,
                        meta=meta,
                        video_json=video_output,
                        title=str(item.get("title") or ""),
                    )
                elif workflow_key in {"dollimages", "dollimagesz"}:
                    self._upload_dollimages_to_cloudinary(
                        prompt_item_id=prompt_item_id,
                        meta=meta,
                        checkpoint_base=checkpoint_base,
                        image_json=up_img or base_img,
                        image_jsons=_select_dollimages_upload_images(
                            base_images=base_images,
                            up_images=up_images,
                            base_img=base_img,
                            up_img=up_img,
                        ),
                        title=str(item.get("title") or ""),
                    )
                elif workflow_key == "anime_v5":
                    self._upload_anime_to_cloudinary(
                        prompt_item_id=prompt_item_id,
                        meta=meta,
                        checkpoint_base=checkpoint_base,
                        image_json=base_img or up_img,
                        image_jsons=_select_dollimages_upload_images(
                            base_images=base_images,
                            up_images=up_images,
                            base_img=base_img,
                            up_img=up_img,
                        ),
                        title=str(item.get("title") or ""),
                    )
                else:
                    self._upload_waifu_to_cloudinary(
                        prompt_item_id=prompt_item_id,
                        meta=meta,
                        checkpoint_base=checkpoint_base,
                        image_json=base_img or up_img,
                        image_jsons=_select_dollimages_upload_images(
                            base_images=base_images,
                            up_images=up_images,
                            base_img=base_img,
                            up_img=up_img,
                        ),
                        title=str(item.get("title") or ""),
                    )

                self._log(f"[WORKER] COMPLETED job_id={job_id} remote_id={remote_id}")
                break

            time.sleep(poll)

        time.sleep(delay_seconds)
        return "PROCESSED"
