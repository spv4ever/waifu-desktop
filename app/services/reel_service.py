from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.services.output_paths import build_output_path
from app.utils.path_sanitize import sanitize_relpath, sanitize_segment


@dataclass(frozen=True)
class ReelCreateResult:
    category: str
    image_count: int
    folder: Path
    video_path: Path
    prompt_item_ids: list[int]


@dataclass(frozen=True)
class _ReelImage:
    prompt_item_id: int
    source_path: Path
    image_json: dict[str, Any]


class ReelService:
    def _select_unused_images(
        self,
        conn,
        *,
        category: str,
        image_count: int,
    ) -> list[_ReelImage]:
        rows = conn.execute(
            """
            SELECT id, base_image_json, upscale_image_json
            FROM prompt_item
            WHERE status = 'DONE'
              AND used_in_reel = 0
              AND (base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)
              AND json_extract(meta_json, '$.combo.category') = ?
            ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
            """,
            (category,),
        ).fetchall()

        selected: list[_ReelImage] = []
        for row in rows:
            image_json = None
            if row["upscale_image_json"]:
                image_json = json.loads(row["upscale_image_json"])
            elif row["base_image_json"]:
                image_json = json.loads(row["base_image_json"])
            if not image_json:
                continue

            source_path = build_output_path(image_json)
            if not source_path.exists():
                continue

            selected.append(
                _ReelImage(
                    prompt_item_id=int(row["id"]),
                    source_path=source_path,
                    image_json=image_json,
                )
            )
            if len(selected) >= image_count:
                break

        return selected

    def _create_reel_folder(self, *, category: str) -> Path:
        category_safe = sanitize_segment(category)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rel_folder = sanitize_relpath(f"anime/Waifu/{category_safe}/reels/reel_{timestamp}")
        folder = Path(settings.comfyui_output_dir) / rel_folder
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _copy_images(self, images: list[_ReelImage], *, folder: Path) -> list[Path]:
        if not images:
            return []
        ext = images[0].source_path.suffix or ".png"
        copied_paths: list[Path] = []
        for idx, image in enumerate(images, start=1):
            target_name = f"frame_{idx:03d}{ext}"
            target_path = folder / target_name
            shutil.copy2(image.source_path, target_path)
            copied_paths.append(target_path)
        return copied_paths

    def _render_video(self, *, folder: Path, ext: str, image_count: int) -> Path:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("No se encontró ffmpeg en el sistema para renderizar el reel.")

        output_path = folder / "reel.mp4"
        pattern = f"frame_%03d{ext}"
        cmd = [
            ffmpeg_path,
            "-y",
            "-framerate",
            "1",
            "-i",
            pattern,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        subprocess.run(cmd, cwd=str(folder), check=True, capture_output=True, text=True)
        return output_path

    def create_reel(
        self,
        conn,
        *,
        category: str,
        image_count: int,
    ) -> ReelCreateResult:
        if image_count <= 0:
            raise ValueError("La cantidad de imágenes debe ser mayor a cero.")

        images = self._select_unused_images(conn, category=category, image_count=image_count)
        if len(images) < image_count:
            raise RuntimeError(
                f"No hay suficientes imágenes disponibles para el reel. "
                f"Disponibles: {len(images)}, solicitadas: {image_count}."
            )

        folder = self._create_reel_folder(category=category)
        copied_paths = self._copy_images(images, folder=folder)
        ext = copied_paths[0].suffix if copied_paths else ".png"
        video_path = self._render_video(folder=folder, ext=ext, image_count=image_count)

        manifest = {
            "category": category,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "image_count": len(images),
            "video": video_path.name,
            "items": [
                {
                    "prompt_item_id": image.prompt_item_id,
                    "source": str(image.source_path),
                    "frame": str(copied_path.name),
                }
                for image, copied_path in zip(images, copied_paths)
            ],
        }
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        ids = [image.prompt_item_id for image in images]
        placeholders = ",".join(["?"] * len(ids))
        conn.execute(
            f"UPDATE prompt_item SET used_in_reel = 1 WHERE id IN ({placeholders})",
            ids,
        )

        return ReelCreateResult(
            category=category,
            image_count=len(images),
            folder=folder,
            video_path=video_path,
            prompt_item_ids=ids,
        )
