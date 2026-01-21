from __future__ import annotations

import json
import time
import sqlite3
from typing import Literal, Any, Callable

from app.data.repositories import QueueRepository, PromptItemRepository
from app.data.kv_store import KVStore
from app.config.settings import settings
from app.services.comfy_client import ComfyClient
from app.services.workflow_service import WorkflowService
from app.config.app_config import load_app_config
from app.utils.path_sanitize import sanitize_segment, sanitize_relpath
from app.services.comfy_history_parser import extract_base_and_upscale


WorkerResult = Literal["PROCESSED", "PAUSED", "EMPTY"]


class QueueWorker:
    def __init__(self, *, log_callback: Callable[[str], None] | None = None) -> None:
        self.queue = QueueRepository()
        self.items = PromptItemRepository()
        self.kv = KVStore()
        self.comfy = ComfyClient()
        self.workflow = WorkflowService()
        self.app_cfg = load_app_config()
        self._log_callback = log_callback

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)

    def _is_finished(self, history: dict[str, Any], prompt_id: str) -> tuple[bool, dict[str, Any] | None]:
        entry = history.get(prompt_id)
        if not entry:
            return False, None

        outputs = entry.get("outputs") or {}
        # Si cualquier output contiene "images", ya terminó y hay ficheros
        for _, out in outputs.items():
            if isinstance(out, dict) and out.get("images"):
                return True, entry

        return False, entry

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

    def process_one(self, conn: sqlite3.Connection, *, delay_seconds: float = 0.2) -> WorkerResult:
        paused = self.kv.get(conn, "queue_paused", "false")
        if paused == "true":
            return "PAUSED"

        job = self.queue.fetch_next_pending(conn)
        if not job:
            return "EMPTY"

        job_id = int(job["id"])
        prompt_item_id = int(job["prompt_item_id"])

        item = self.items.get_by_id(conn, prompt_item_id)
        if not item:
            with conn:
                self.queue.mark_failed(conn, job_id, f"prompt_item_id={prompt_item_id} no existe")
            return "PROCESSED"

        meta = json.loads(item["meta_json"]) if item.get("meta_json") else {}
        combo = meta.get("combo", {})
        checkpoints = meta.get("checkpoints", {}) if isinstance(meta.get("checkpoints"), dict) else {}
        checkpoint_base = checkpoints.get("base")
        checkpoint_refiner = checkpoints.get("refiner")

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
        remote_id = job.get("remote_id")
        if not remote_id:
            wf = self.workflow.load_template()

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
            )

            remote_id = self.comfy.submit_prompt(wf)
            with conn:
                self.queue.set_remote(conn, job_id, remote_id, "SUBMITTED")
            self._log(f"[WORKER] SUBMITTED job_id={job_id} remote_id={remote_id}")

        # 2) POLL hasta terminar (sin saturar, 1 en vuelo)
        poll = float(settings.comfyui_poll_interval)
        last_progress: int | None = None
        while True:
            paused = self.kv.get(conn, "queue_paused", "false")
            if paused == "true":
                self._log("[WORKER] Pausado durante polling. Se reanudará más tarde.")
                with conn:
                    self.queue.set_remote_status(conn, job_id, "PAUSED_WAITING")
                return "PROCESSED"

            history = self.comfy.get_history(remote_id)
            finished, entry = self._is_finished(history, remote_id)

            if entry:
                progress = self._extract_progress(entry)
                if progress is not None and progress != last_progress:
                    last_progress = progress
                    with conn:
                        self.queue.set_progress(conn, job_id, progress)

            if finished and entry:
                base_img, up_img = extract_base_and_upscale(entry)

                with conn:
                    self.queue.set_remote_status(conn, job_id, "COMPLETED")
                    self.queue.set_output_json(conn, job_id, json.dumps(entry, ensure_ascii=False))
                    self.queue.set_progress(conn, job_id, 100)

                    # Guardar outputs en prompt_item
                    self.items.set_outputs(
                        conn,
                        item_id=prompt_item_id,
                        base_image_json=json.dumps(base_img, ensure_ascii=False) if base_img else None,
                        upscale_image_json=json.dumps(up_img, ensure_ascii=False) if up_img else None,
                    )

                    self.queue.mark_done(conn, job_id)
                    self.items.bulk_update_status(conn, ids=[prompt_item_id], status="DONE")

                self._log(f"[WORKER] COMPLETED job_id={job_id} remote_id={remote_id}")
                break

            time.sleep(poll)

        time.sleep(delay_seconds)
        return "PROCESSED"
