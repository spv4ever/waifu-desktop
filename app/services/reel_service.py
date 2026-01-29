from __future__ import annotations

import json
import random
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config.waifu_catalog import load_waifu_catalog
from app.config.settings import settings
from app.services.output_paths import build_output_path
from app.utils.path_sanitize import sanitize_relpath, sanitize_segment


@dataclass(frozen=True)
class ReelCreateResult:
    category: str
    variant: str | None
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
    _OUTPUT_WIDTH = 1080
    _OUTPUT_HEIGHT = 1920
    _TRANSITION_SECONDS = 0.5
    _FADE_OUT_SECONDS = 0.5
    _FPS = 30
    _TITLE_FONT_SIZE = 64
    _SOCIAL_FONT_SIZE = 60
    _CTA_FONT_SIZE = 84

    def _wrap_text_two_lines(self, text: str, *, max_chars: int) -> str:
        if "\\n" in text or "/n" in text or "\\\\n" in text:
            for marker in ("\\\\n", "\\n", "/n"):
                text = text.replace(marker, "\n")
        if "\n" in text:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                if len(lines) == 1:
                    text = lines[0]
                else:
                    return "\n".join(lines[:2])
        clean_text = " ".join(text.split())
        if len(clean_text) <= max_chars:
            return clean_text
        for separator in (" | ", " • "):
            if separator in clean_text:
                parts = [part.strip() for part in clean_text.split(separator) if part.strip()]
                if len(parts) > 1:
                    midpoint = (len(parts) + 1) // 2
                    return separator.join(parts[:midpoint]) + "\n" + separator.join(parts[midpoint:])
        words = clean_text.split()
        if len(words) <= 1:
            return clean_text
        best_split: tuple[str, str] | None = None
        best_score: tuple[int, int, int] | None = None
        for split_idx in range(1, len(words)):
            line_one = " ".join(words[:split_idx])
            line_two = " ".join(words[split_idx:])
            max_len = max(len(line_one), len(line_two))
            overage = max(0, max_len - max_chars)
            balance = abs(len(line_one) - len(line_two))
            score = (overage, max_len, balance)
            if best_score is None or score < best_score:
                best_score = score
                best_split = (line_one, line_two)
        if best_split is None:
            return clean_text
        return f"{best_split[0]}\n{best_split[1]}"

    def _format_reel_text(self, text: str, *, max_chars: int, font_size: int, reduce_by: int) -> tuple[str, int]:
        wrapped = self._wrap_text_two_lines(text, max_chars=max_chars)
        lines = [line for line in wrapped.splitlines() if line]
        max_len = max((len(line) for line in lines), default=0)
        adjusted_font = font_size
        if "\n" in wrapped:
            adjusted_font = max(adjusted_font - reduce_by, 12)
        if max_len > max_chars:
            adjusted_font = max(adjusted_font - ((max_len - max_chars) * 4), 12)
        return wrapped, adjusted_font

    def _select_reel_title(self, *, category_key: str) -> str | None:
        catalog = load_waifu_catalog()
        titles_config = catalog.raw.get("reel_titles", {})
        title_templates: list[str] = []
        if isinstance(titles_config, list):
            title_templates = [str(item) for item in titles_config if item]
        elif isinstance(titles_config, dict):
            for key in (category_key, "default"):
                value = titles_config.get(key)
                if isinstance(value, list):
                    title_templates = [str(item) for item in value if item]
                    if title_templates:
                        break

        if not title_templates:
            return None

        category_label = str(catalog.categories.get(category_key, {}).get("label", category_key)).strip()
        if not category_label:
            category_label = category_key

        template = random.choice(title_templates)
        if "{category}" in template:
            return template.replace("{category}", category_label)
        return f"{category_label} {template}".strip()

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        return (
            text.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(":", "\\:")
            .replace("'", "\\'")
        )

    def _build_social_text(self) -> str:
        x_handle = (settings.reel_x_handle or "").strip()
        if x_handle:
            return f"X: {x_handle}"
        return "X"

    def _drawtext_filter(self, text: str, *, font_size: int, y_expr: str, line_spacing: int = 8) -> str:
        escaped_text = self._escape_drawtext(text)
        return (
            f"drawtext=text='{escaped_text}':fontcolor=white:fontsize={font_size}:"
            f"box=1:boxcolor=black@0.45:boxborderw=20:line_spacing={line_spacing}:"
            f"x=(w-text_w)/2:y={y_expr}"
        )

    def _select_unused_images(
        self,
        conn,
        *,
        category: str,
        variant: str | None,
        image_count: int,
    ) -> list[_ReelImage]:
        conditions = [
            "status = 'DONE'",
            "used_in_reel = 0",
            "(base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL)",
            "json_extract(meta_json, '$.combo.category') = ?",
        ]
        params: list[str] = [category]
        if variant:
            conditions.append("json_extract(meta_json, '$.combo.variant') = ?")
            params.append(variant)

        rows = conn.execute(
            f"""
            SELECT id, base_image_json, upscale_image_json
            FROM prompt_item
            WHERE {' AND '.join(conditions)}
            ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
            """,
            params,
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

    def _create_reel_folder(self, *, category: str, variant: str | None) -> Path:
        category_safe = sanitize_segment(category)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if variant:
            variant_safe = sanitize_segment(variant)
            rel_folder = sanitize_relpath(f"anime/Waifu/{category_safe}/{variant_safe}/reels/reel_{timestamp}")
        else:
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

    def _select_audio_fragment(self, *, total_duration: float) -> tuple[Path, float, bool] | None:
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
                duration = float(probe.stdout.strip())
                if duration > total_duration:
                    start_time = random.uniform(0.0, max(duration - total_duration, 0.0))
                else:
                    loop_audio = True
            except (ValueError, subprocess.CalledProcessError):
                loop_audio = True
        else:
            loop_audio = True

        return audio_path, start_time, loop_audio

    def _render_video(
        self,
        *,
        folder: Path,
        ext: str,
        image_count: int,
        seconds_per_image: float,
        title: str | None,
    ) -> tuple[Path, Path | None]:
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("No se encontró ffmpeg en el sistema para renderizar el reel.")

        output_path = folder / "reel.mp4"
        total_duration = (image_count * seconds_per_image) - ((image_count - 1) * self._TRANSITION_SECONDS)
        total_duration = max(total_duration, seconds_per_image)
        fade_out_start = max(total_duration - self._FADE_OUT_SECONDS, 0.0)

        cmd = [ffmpeg_path, "-y"]
        for idx in range(1, image_count + 1):
            cmd += [
                "-loop",
                "1",
                "-t",
                f"{seconds_per_image}",
                "-i",
                f"frame_{idx:03d}{ext}",
            ]

        audio_selection = self._select_audio_fragment(total_duration=total_duration)
        selected_audio_path: Path | None = None
        if audio_selection:
            audio_path, start_time, loop_audio = audio_selection
            selected_audio_path = audio_path
            if loop_audio:
                cmd += ["-stream_loop", "-1"]
            cmd += ["-ss", f"{start_time}", "-t", f"{total_duration}", "-i", str(audio_path)]

        social_text = self._build_social_text()
        social_text, social_font = self._format_reel_text(
            social_text,
            max_chars=26,
            font_size=self._SOCIAL_FONT_SIZE,
            reduce_by=8,
        )
        cta_text, cta_font = self._format_reel_text(
            "Follow • Reply • Like",
            max_chars=24,
            font_size=self._CTA_FONT_SIZE,
            reduce_by=16,
        )
        title_text = None
        title_font = self._TITLE_FONT_SIZE
        if title:
            title_text, title_font = self._format_reel_text(
                title,
                max_chars=16,
                font_size=self._TITLE_FONT_SIZE,
                reduce_by=8,
            )
        filter_parts: list[str] = []
        for idx in range(image_count):
            filters = (
                f"[{idx}:v]scale={self._OUTPUT_WIDTH}:{self._OUTPUT_HEIGHT}"
                f":force_original_aspect_ratio=decrease,"
                f"pad={self._OUTPUT_WIDTH}:{self._OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps={self._FPS},setsar=1"
            )
            is_last = idx == image_count - 1
            is_penultimate = idx == image_count - 2
            if title_text and idx < image_count - 2:
                filters += f",{self._drawtext_filter(title_text, font_size=title_font, y_expr='h*0.12')}"
            elif is_penultimate:
                filters += f",{self._drawtext_filter(social_text, font_size=social_font, y_expr='h*0.12')}"
            if is_last:
                filters += f",{self._drawtext_filter(social_text, font_size=social_font, y_expr='h*0.12')}"
                filters += f",{self._drawtext_filter(cta_text, font_size=cta_font, y_expr='h*0.22')}"
            filters += ",format=rgba"
            filter_parts.append(f"{filters}[v{idx}]")

        current_label = "v0"
        offset = seconds_per_image - self._TRANSITION_SECONDS
        for idx in range(1, image_count):
            next_label = f"v{idx}"
            out_label = f"vxf{idx}"
            filter_parts.append(
                (
                    f"[{current_label}][{next_label}]"
                    f"xfade=transition=fade:duration={self._TRANSITION_SECONDS}:offset={offset}"
                    f"[{out_label}]"
                )
            )
            current_label = out_label
            offset += seconds_per_image - self._TRANSITION_SECONDS

        filter_parts.append(
            f"[{current_label}]fade=t=out:st={fade_out_start}:d={self._FADE_OUT_SECONDS},format=yuv420p[v]"
        )

        audio_label = None
        if audio_selection:
            audio_label = "a"
            filter_parts.append(
                f"[{image_count}:a]volume=0.5,"
                f"afade=t=out:st={fade_out_start}:d={self._FADE_OUT_SECONDS}[{audio_label}]"
            )

        filter_complex = ";".join(filter_parts)

        cmd = [
            *cmd,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ]
        if audio_selection:
            cmd += [
                "-map",
                f"[{audio_label}]",
                "-c:a",
                "aac",
                "-shortest",
            ]
        cmd.append(str(output_path))
        subprocess.run(cmd, cwd=str(folder), check=True, capture_output=True, text=True)
        return output_path, selected_audio_path

    def create_reel(
        self,
        conn,
        *,
        category: str,
        variant: str | None,
        image_count: int,
        seconds_per_image: float,
    ) -> ReelCreateResult:
        if image_count <= 0:
            raise ValueError("La cantidad de imágenes debe ser mayor a cero.")
        if seconds_per_image <= 0:
            raise ValueError("Los segundos por imagen deben ser mayores a cero.")
        if seconds_per_image <= self._TRANSITION_SECONDS:
            raise ValueError("Los segundos por imagen deben ser mayores a la duración de la transición.")

        images = self._select_unused_images(
            conn,
            category=category,
            variant=variant,
            image_count=image_count,
        )
        if len(images) < image_count:
            raise RuntimeError(
                f"No hay suficientes imágenes disponibles para el reel. "
                f"Disponibles: {len(images)}, solicitadas: {image_count}."
            )

        folder = self._create_reel_folder(category=category, variant=variant)
        copied_paths = self._copy_images(images, folder=folder)
        ext = copied_paths[0].suffix if copied_paths else ".png"
        title = self._select_reel_title(category_key=category)
        video_path, audio_path = self._render_video(
            folder=folder,
            ext=ext,
            image_count=image_count,
            seconds_per_image=seconds_per_image,
            title=title,
        )

        manifest = {
            "category": category,
            "variant": variant,
            "title": title,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "image_count": len(images),
            "seconds_per_image": seconds_per_image,
            "transition_seconds": self._TRANSITION_SECONDS,
            "video": video_path.name,
            "audio": audio_path.name if audio_path else None,
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
            variant=variant,
            image_count=len(images),
            folder=folder,
            video_path=video_path,
            prompt_item_ids=ids,
        )
