from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from math import ceil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.data.storage import get_store
from app.services.output_paths import build_output_path


@dataclass(frozen=True)
class VideoMontageResult:
    folder: Path
    video_path: Path
    source_videos: list[Path]
    audio_path: Path | None
    duration_seconds: float
    ratio: str


@dataclass(frozen=True)
class BulkImagesYoutubeVideoResult:
    folder: Path
    video_path: Path
    source_images: list[Path]
    prompt_item_ids: list[int]
    audio_path: Path
    duration_seconds: float
    image_display_seconds: float
    resolution: str
    bulk_category: str
    transition_seconds: float
    transition_type: str
    youtube_copy_path: Path


@dataclass(frozen=True)
class BulkYoutubePlan:
    audio_duration_seconds: float
    image_display_seconds: float
    transition_seconds: float
    transition_type: str
    needed_images: int
    available_images: int


class VideoMontageService:
    """Renderiza montajes por concatenación de varios vídeos con fundidos y música."""

    _FPS = 30
    _TRANSITION_SECONDS = 0.75
    _FADE_OUT_SECONDS = 0.5
    _AUDIO_RANDOM_START_WINDOW_SECONDS = 60.0
    _RATIO_SIZES = {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
    }
    _VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    _YOUTUBE_4K_SIZE = (3840, 2160)
    _YOUTUBE_IMAGE_SECONDS = 8.0
    _YOUTUBE_TRANSITIONS = {"fade", "fadeblack", "fadewhite", "distance", "wipeleft", "wiperight", "wipeup", "wipedown", "slideleft", "slideright", "slideup", "slidedown", "circleopen", "circleclose", "dissolve", "pixelize"}
    _VIDEO_TRANSITIONS = _YOUTUBE_TRANSITIONS
    _FFMPEG_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
    _YOUTUBE_COPY_TEMPLATES = (
        (
            "{song_title} 🌙 Música Relajante para Desconectar",
            "Disfruta de {song_title}, una pieza musical creada para acompañar momentos de calma, descanso y desconexión. Ideal para escuchar al terminar el día, relajarte o simplemente disfrutar de unos minutos de tranquilidad. 🎵 La música y las imágenes de este vídeo han sido creadas mediante inteligencia artificial. La selección, edición y montaje final han sido realizados para ofrecer una experiencia visual y musical agradable.",
            "música relajante, canción relajante, música para desconectar, música tranquila, relajación, calma, descanso, música ambiental, música instrumental, música creada con IA, imágenes creadas con IA, AI generated music, relaxing music, calm music",
        ),
        (
            "{song_title} ✨ Música Suave para Relajarse",
            "Haz una pausa y disfruta de {song_title}, una composición suave pensada para crear un ambiente tranquilo y relajante. Puedes escucharla mientras descansas, lees, trabajas o buscas unos minutos de calma. 🎵 Tanto la música como las imágenes utilizadas en este vídeo han sido generadas con herramientas de inteligencia artificial. La edición y el montaje final han sido realizados manualmente.",
            "música suave, música relajante, música para relajarse, canción tranquila, ambiente relajante, música de fondo, relax music, soft music, peaceful music, música IA, música generada por IA, imágenes IA, AI music, AI generated images",
        ),
        (
            "{song_title} 🧘 Música para Meditación y Calma Interior",
            "{song_title} es una pieza de música relajante diseñada para acompañar sesiones de meditación, respiración consciente o momentos de calma personal. Escúchala a un volumen cómodo y permite que la música te ayude a desconectar. 🎵 Música e imágenes creadas mediante inteligencia artificial. Edición, selección y montaje realizados para construir una experiencia relajante y envolvente.",
            "música para meditar, música de meditación, calma interior, relajación profunda, mindfulness, respiración consciente, música tranquila, meditation music, relaxing meditation, peaceful music, AI generated music, música creada con IA, imágenes generadas por IA",
        ),
        (
            "{song_title} 💫 Música Relajante para Reducir el Estrés",
            "Regálate unos minutos de tranquilidad con {song_title}, una composición musical suave pensada para ayudarte a desconectar del ritmo diario y crear una atmósfera de calma. Ideal para descansar después del trabajo o acompañar tus momentos de relajación. 🎵 La música y las imágenes de este vídeo han sido generadas mediante inteligencia artificial. El montaje y la edición final han sido realizados manualmente.",
            "música para reducir estrés, música antiestrés, música relajante, relajación mental, música tranquila, descanso, música ambiental, stress relief music, relaxing music, calm music, música generada por IA, AI music, imágenes generadas por IA",
        ),
        (
            "{song_title} 📖 Música Tranquila para Leer y Estudiar",
            "Acompaña tus momentos de lectura, estudio o concentración con {song_title}. Una pieza instrumental suave que puede ayudarte a crear un ambiente tranquilo, agradable y libre de distracciones. 🎵 Tanto la música como las imágenes de este vídeo han sido creadas utilizando inteligencia artificial. La selección, edición y composición final del vídeo han sido realizadas manualmente.",
            "música para estudiar, música para leer, música para concentrarse, música tranquila, música instrumental, música de fondo, study music, reading music, focus music, relaxing music, AI generated music, música creada con IA, imágenes creadas con IA",
        ),
        (
            "{song_title} 🌌 Música Ambiental para Descansar",
            "Déjate acompañar por {song_title}, una pieza de música ambiental creada para ofrecer unos minutos de calma y descanso. Ideal para escuchar con auriculares, relajarte en casa o crear una atmósfera tranquila. 🎵 La música y las imágenes han sido generadas con herramientas de inteligencia artificial. La edición y el montaje final han sido realizados para dar forma a una experiencia audiovisual única.",
            "música ambiental, ambient music, música para descansar, música relajante, canción instrumental, atmósfera tranquila, música de fondo, relaxing ambient music, calm ambience, AI generated music, AI generated art, música IA, imágenes IA",
        ),
        (
            "{song_title} 😌 Un Momento de Paz y Relajación",
            "Detén el ritmo durante unos minutos y disfruta de {song_title}, una composición tranquila pensada para acompañar momentos de paz, reflexión y descanso. Una pequeña pausa musical para desconectar de las preocupaciones diarias. 🎵 Música e imágenes generadas mediante inteligencia artificial. La edición, organización y montaje final del contenido han sido realizados manualmente.",
            "momento de paz, música de relajación, música tranquila, música para descansar, canción relajante, música para desconectar, peaceful music, relaxation music, calming music, AI music, música generada por IA, imágenes creadas con IA, inteligencia artificial",
        ),
        (
            "{song_title} 🌙 Música Relajante para el Final del Día",
            "Termina el día con {song_title}, una pieza musical suave creada para acompañar tus momentos de descanso y desconexión. Baja el volumen, ponte cómodo y disfruta de unos minutos de tranquilidad. 🎵 Tanto la música como las imágenes mostradas en este vídeo han sido creadas con inteligencia artificial. La edición y el montaje final han sido realizados manualmente.",
            "música para el final del día, música nocturna, música relajante, música tranquila, descanso nocturno, música para desconectar, evening relaxation music, night music, calm music, AI generated music, música creada con IA, imágenes generadas por IA",
        ),
        (
            "{song_title} 🎧 Música Instrumental para Relajarse",
            "Escucha {song_title}, una composición instrumental de ambiente tranquilo pensada para relajarte, trabajar con calma o disfrutar de un momento personal sin distracciones. Recomendamos utilizar auriculares para una experiencia más envolvente. 🎵 La música y las imágenes de este vídeo han sido generadas con inteligencia artificial. La edición y el montaje audiovisual han sido realizados manualmente.",
            "música instrumental, instrumental relajante, música para relajarse, música de fondo, canción instrumental, música tranquila, relaxing instrumental music, background music, calm instrumental, música IA, AI generated music, AI generated images",
        ),
        (
            "{song_title} 🌿 Música para una Pausa Relajante",
            "Haz una pequeña pausa con {song_title}, una pieza musical creada para aportar calma y acompañar momentos de descanso, lectura, reflexión o relajación. Respira profundamente y disfruta de la música. 🎵 La música y las imágenes de este vídeo han sido generadas mediante herramientas de inteligencia artificial. La edición, selección y montaje final han sido realizados manualmente.",
            "pausa relajante, música para relajarse, música tranquila, relajación, canción de relajación, música ambiental, calm music, relaxing music, peaceful instrumental, AI generated music, música generada por IA, imágenes generadas por IA, arte IA",
        ),
    )

    def _write_youtube_copy(self, folder: Path, output_stem: str, primary_audio: Path) -> tuple[Path, dict[str, str]]:
        song_title = re.sub(r"[_-]+", " ", primary_audio.stem).strip() or "Música Relajante"
        title_template, description_template, tags = random.choice(self._YOUTUBE_COPY_TEMPLATES)
        copy = {
            "title": title_template.format(song_title=song_title),
            "description": description_template.format(song_title=song_title),
            "tags": tags,
        }
        copy_path = folder / f"{output_stem}.txt"
        copy_path.write_text(
            f"TÍTULO\n{copy['title']}\n\nDESCRIPCIÓN\n{copy['description']}\n\nETIQUETAS\n{copy['tags']}\n",
            encoding="utf-8",
        )
        return copy_path, copy

    def _emit_progress(self, progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback:
            progress_callback(message)

    def _format_eta(self, seconds: float | None) -> str:
        if seconds is None or seconds <= 0:
            return "calculando..."
        minutes, secs = divmod(int(round(seconds)), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes:02d}m {secs:02d}s"
        if minutes:
            return f"{minutes}m {secs:02d}s"
        return f"{secs}s"

    def _parse_ffmpeg_time(self, line: str) -> float | None:
        match = self._FFMPEG_TIME_RE.search(line)
        if not match:
            return None
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        return (hours * 3600) + (minutes * 60) + seconds

    def _run_ffmpeg_render(
        self,
        cmd: list[str],
        *,
        cwd: Path,
        total_seconds: float,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        if not progress_callback:
            subprocess.run(
                cmd,
                cwd=str(cwd),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return

        started_at = time.monotonic()
        last_percent = -1
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        output_lines: list[str] = []
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if line:
                output_lines.append(line)
            rendered_seconds = self._parse_ffmpeg_time(line)
            if rendered_seconds is None:
                continue
            progress = min(max(rendered_seconds / max(total_seconds, 0.001), 0.0), 1.0)
            percent = int(progress * 100)
            if percent == last_percent and percent < 100:
                continue
            last_percent = percent
            elapsed = time.monotonic() - started_at
            eta = (elapsed / progress) - elapsed if progress > 0 else None
            self._emit_progress(
                progress_callback,
                f"Renderizando: {percent}% ({rendered_seconds:.1f}s/{total_seconds:.1f}s) · ETA {self._format_eta(eta)}",
            )
        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, cmd, output="\n".join(output_lines))

    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _output_root(self) -> Path:
        root = self._repo_root() / "outputs" / "video_montage"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _create_folder(self) -> Path:
        folder = self._output_root() / datetime.now().strftime("%Y%m%d_%H%M%S")
        counter = 1
        original = folder
        while folder.exists():
            counter += 1
            folder = Path(f"{original}_{counter}")
        folder.mkdir(parents=True, exist_ok=False)
        return folder

    def _probe_duration(self, path: Path) -> float:
        ffprobe_path = shutil.which("ffprobe")
        if not ffprobe_path:
            raise RuntimeError("No se encontró ffprobe en el sistema para calcular duraciones.")
        probe = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return max(float(probe.stdout.strip()), 0.0)

    def _select_audio_track(self) -> tuple[Path, float] | None:
        audio_dir = self._repo_root() / "resources" / "audio"
        if not audio_dir.exists():
            return None
        audio_files = sorted(path for path in audio_dir.glob("*.mp3") if path.is_file())
        if not audio_files:
            return None
        audio_path = random.choice(audio_files)
        audio_duration = self._probe_duration(audio_path)
        max_start_time = min(
            self._AUDIO_RANDOM_START_WINDOW_SECONDS,
            max(audio_duration - 1.0, 0.0),
        )
        start_time = random.uniform(0.0, max_start_time) if max_start_time > 0 else 0.0
        return audio_path, start_time

    def _audio_relax_dir(self) -> Path:
        return self._repo_root() / "resources" / "audio_relax"

    def _safe_filename_segment(self, value: str) -> str:
        segment = re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE).strip("._-")
        return segment or "audio"

    def _resolve_audio_relax_track(self, audio_filename: str | Path) -> Path:
        audio_path = Path(audio_filename).expanduser()
        if not audio_path.is_absolute():
            audio_path = self._audio_relax_dir() / audio_path
        audio_path = audio_path.resolve()
        audio_dir = self._audio_relax_dir().resolve()
        if not audio_path.exists() or not audio_path.is_file():
            raise FileNotFoundError(f"No existe el audio MP3: {audio_path}")
        if audio_path.suffix.lower() != ".mp3":
            raise ValueError("El audio debe ser un archivo .mp3 de resources/audio_relax.")
        if audio_dir not in audio_path.parents:
            raise ValueError("El audio debe estar dentro de resources/audio_relax.")
        return audio_path

    def _select_unused_bulk_images(
        self,
        *,
        bulk_category: str,
        image_count: int,
    ) -> list[tuple[int, Path, dict[str, Any]]]:
        store = get_store()
        rows = store.select_unused_bulk_images_for_youtube_video(bulk_category=bulk_category)
        random.shuffle(rows)

        selected: list[tuple[int, Path, dict[str, Any]]] = []
        for row in rows:
            image_json = None
            if row.get("upscale_image_json"):
                image_json = json.loads(row["upscale_image_json"])
            elif row.get("base_image_json"):
                image_json = json.loads(row["base_image_json"])
            if not image_json:
                continue

            source_path = build_output_path(image_json)
            if not source_path.exists() or source_path.suffix.lower() not in self._IMAGE_EXTENSIONS:
                continue

            selected.append((int(row["id"]), source_path, image_json))
            if len(selected) >= image_count:
                break
        return selected


    def calculate_bulk_youtube_plan(
        self,
        *,
        bulk_category: str,
        audio_filename: str | Path,
        second_audio_filename: str | Path | None = None,
        image_display_seconds: float | None = None,
        transition_seconds: float | None = None,
        transition_type: str = "fade",
    ) -> BulkYoutubePlan:
        clean_category = str(bulk_category).strip()
        audio_path = self._resolve_audio_relax_track(audio_filename)
        audio_duration = self._probe_duration(audio_path)
        if second_audio_filename:
            second_audio_path = self._resolve_audio_relax_track(second_audio_filename)
            audio_duration += self._probe_duration(second_audio_path)
        if audio_duration <= 0:
            raise ValueError("No se pudo calcular la duración del MP3 seleccionado.")
        transition_seconds = self._TRANSITION_SECONDS if transition_seconds is None else max(float(transition_seconds), 0.0)
        image_display_seconds = (
            self._YOUTUBE_IMAGE_SECONDS
            if image_display_seconds is None
            else max(float(image_display_seconds), transition_seconds + 0.25)
        )
        clean_transition = str(transition_type or "fade").strip().lower()
        if clean_transition not in self._YOUTUBE_TRANSITIONS:
            clean_transition = "fade"
        effective_seconds = max(image_display_seconds - transition_seconds, 0.25)
        needed_images = max(1, ceil(max(audio_duration - transition_seconds, 0.0) / effective_seconds))
        available_images = len(self._select_unused_bulk_images(bulk_category=clean_category, image_count=10**9)) if clean_category else 0
        return BulkYoutubePlan(
            audio_duration_seconds=audio_duration,
            image_display_seconds=image_display_seconds,
            transition_seconds=transition_seconds,
            transition_type=clean_transition,
            needed_images=needed_images,
            available_images=available_images,
        )

    def create_bulk_images_youtube_video(
        self,
        *,
        bulk_category: str,
        audio_filename: str | Path,
        second_audio_filename: str | Path | None = None,
        image_display_seconds: float | None = None,
        transition_seconds: float | None = None,
        resolution: str = "4k",
        transition_type: str = "fade",
        progress_callback: Callable[[str], None] | None = None,
    ) -> BulkImagesYoutubeVideoResult:
        """Crea un vídeo 16:9 usando uno o dos temas MP3 completos."""
        clean_category = str(bulk_category).strip()
        if not clean_category:
            raise ValueError("Selecciona una categoría de Bulk Images.")

        self._emit_progress(progress_callback, "Validando audio seleccionado...")
        source_audio_paths = [self._resolve_audio_relax_track(audio_filename)]
        if second_audio_filename:
            source_audio_paths.append(self._resolve_audio_relax_track(second_audio_filename))
        source_audio_durations = [self._probe_duration(path) for path in source_audio_paths]
        audio_duration = sum(source_audio_durations)
        audio_names = " + ".join(path.name for path in source_audio_paths)
        self._emit_progress(progress_callback, f"Audio: {audio_names} · duración final {audio_duration:.1f}s")
        if audio_duration <= 0:
            raise ValueError("No se pudo calcular la duración del MP3 seleccionado.")

        transition_seconds = self._TRANSITION_SECONDS if transition_seconds is None else max(float(transition_seconds), 0.0)
        image_display_seconds = (
            self._YOUTUBE_IMAGE_SECONDS
            if image_display_seconds is None
            else max(float(image_display_seconds), transition_seconds + 0.25)
        )
        clean_transition = str(transition_type or "fade").strip().lower()
        if clean_transition not in self._YOUTUBE_TRANSITIONS:
            raise ValueError("Transición no soportada para el vídeo YouTube Bulk Images.")
        effective_seconds = max(image_display_seconds - transition_seconds, 0.25)
        image_count = max(1, ceil(max(audio_duration - transition_seconds, 0.0) / effective_seconds))

        self._emit_progress(progress_callback, f"Seleccionando {image_count} imágenes sin usar de la categoría {clean_category}...")
        selected = self._select_unused_bulk_images(bulk_category=clean_category, image_count=image_count)
        if len(selected) < image_count:
            raise RuntimeError(
                "No hay suficientes imágenes sin usar para cubrir toda la canción. "
                f"Necesarias={image_count}, disponibles={len(selected)}."
            )

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("No se encontró ffmpeg en el sistema para renderizar el vídeo.")

        width, height = self._YOUTUBE_4K_SIZE if resolution.lower() == "4k" else self._RATIO_SIZES["16:9"]
        self._emit_progress(progress_callback, f"Preparando render {width}x{height} con transición {clean_transition}...")
        folder = self._create_folder()
        audio_theme_slug = "_".join(self._safe_filename_segment(path.stem) for path in source_audio_paths)
        output_stem = f"bulk_images_youtube_{audio_theme_slug}"
        output_path = folder / f"{output_stem}.mp4"
        paths = [path for _, path, _ in selected]

        audio_path = source_audio_paths[0]
        if len(source_audio_paths) == 2:
            audio_path = folder / f"tema_final_{audio_theme_slug}.mp3"
            self._emit_progress(progress_callback, "Uniendo los dos temas en el tema final...")
            merge_cmd = [ffmpeg_path, "-y"]
            for source_path in source_audio_paths:
                merge_cmd += ["-i", str(source_path)]
            merge_cmd += [
                "-filter_complex",
                "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
                "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
                "[a0][a1]concat=n=2:v=0:a=1[a]",
                "-map",
                "[a]",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                str(audio_path),
            ]
            subprocess.run(
                merge_cmd,
                cwd=str(folder),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        cmd = [ffmpeg_path, "-y"]
        for path in paths:
            cmd += ["-loop", "1", "-t", f"{image_display_seconds:.3f}", "-i", str(path)]
        audio_input_index = len(paths)
        cmd += ["-i", str(audio_path)]

        filter_parts: list[str] = []
        for idx in range(len(paths)):
            filter_parts.append(
                f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={self._FPS},format=yuv420p[v{idx}]"
            )

        current_label = "v0"
        current_duration = image_display_seconds
        for idx in range(1, len(paths)):
            out_label = f"xf{idx}"
            offset = max(current_duration - transition_seconds, 0.0)
            filter_parts.append(
                f"[{current_label}][v{idx}]xfade=transition={clean_transition}:duration={transition_seconds:.3f}:"
                f"offset={offset:.3f}[{out_label}]"
            )
            current_label = out_label
            current_duration += image_display_seconds - transition_seconds

        fade_out_start = max(audio_duration - self._FADE_OUT_SECONDS, 0.0)
        filter_parts.append(
            f"[{current_label}]trim=0:{audio_duration:.3f},setpts=PTS-STARTPTS,"
            f"fade=t=out:st={fade_out_start:.3f}:d={self._FADE_OUT_SECONDS}[v]"
        )
        filter_parts.append(
            f"[{audio_input_index}:a]atrim=0:{audio_duration:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=out:st={fade_out_start:.3f}:d={self._FADE_OUT_SECONDS}[a]"
        )

        cmd += [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-t",
            f"{audio_duration:.3f}",
            str(output_path),
        ]
        self._emit_progress(progress_callback, "Iniciando FFmpeg...")
        self._run_ffmpeg_render(cmd, cwd=folder, total_seconds=audio_duration, progress_callback=progress_callback)
        self._emit_progress(progress_callback, "Render finalizado. Marcando imágenes como usadas...")

        prompt_item_ids = [prompt_id for prompt_id, _, _ in selected]
        get_store().mark_prompt_items_used_in_reel(prompt_item_ids)
        youtube_copy_path, youtube_copy = self._write_youtube_copy(folder, output_stem, source_audio_paths[0])

        metadata = {
            "bulk_category": clean_category,
            "audio": str(audio_path),
            "source_audios": [str(path) for path in source_audio_paths],
            "duration_seconds": audio_duration,
            "image_display_seconds": image_display_seconds,
            "transition_seconds": transition_seconds,
            "transition_type": clean_transition,
            "resolution": {"label": resolution, "width": width, "height": height},
            "prompt_item_ids": prompt_item_ids,
            "source_images": [str(path) for path in paths],
            "youtube_copy": youtube_copy,
            "youtube_copy_path": str(youtube_copy_path),
        }
        (folder / f"{output_stem}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        self._emit_progress(progress_callback, f"Vídeo creado correctamente: {output_path}")

        return BulkImagesYoutubeVideoResult(
            folder=folder,
            video_path=output_path,
            source_images=paths,
            prompt_item_ids=prompt_item_ids,
            audio_path=audio_path,
            duration_seconds=audio_duration,
            image_display_seconds=image_display_seconds,
            resolution=resolution,
            bulk_category=clean_category,
            transition_seconds=transition_seconds,
            transition_type=clean_transition,
            youtube_copy_path=youtube_copy_path,
        )

    def create_montage(
        self,
        *,
        source_videos: list[str | Path],
        ratio: str,
        transition_seconds: float | None = None,
        transition_type: str = "fade",
        fade_out: bool = True,
    ) -> VideoMontageResult:
        if ratio not in self._RATIO_SIZES:
            raise ValueError("Ratio no soportado. Usa 9:16 o 16:9.")

        paths = [Path(item).expanduser().resolve() for item in source_videos]
        if len(paths) < 2:
            raise ValueError("Añade al menos dos vídeos para montar.")
        for path in paths:
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"No existe el vídeo: {path}")
            if path.suffix.lower() not in self._VIDEO_EXTENSIONS:
                raise ValueError(f"Formato de vídeo no soportado: {path.name}")

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("No se encontró ffmpeg en el sistema para renderizar el montaje.")

        transition_seconds = self._TRANSITION_SECONDS if transition_seconds is None else max(float(transition_seconds), 0.0)
        clean_transition = str(transition_type or "fade").strip().lower()
        if clean_transition not in self._VIDEO_TRANSITIONS:
            raise ValueError("Tipo de transición no soportado.")
        width, height = self._RATIO_SIZES[ratio]
        durations = [self._probe_duration(path) for path in paths]
        if transition_seconds > 0 and any(duration <= transition_seconds for duration in durations):
            raise ValueError("La transición debe durar menos que cada vídeo del montaje.")
        total_duration = sum(durations) - (transition_seconds * max(len(paths) - 1, 0))
        fade_out_start = max(total_duration - self._FADE_OUT_SECONDS, 0.0) if fade_out else 0.0

        folder = self._create_folder()
        output_path = folder / "montaje.mp4"
        audio_selection = self._select_audio_track()
        audio_path = audio_selection[0] if audio_selection else None
        audio_start_time = audio_selection[1] if audio_selection else 0.0

        cmd = [ffmpeg_path, "-y"]
        for path in paths:
            cmd += ["-i", str(path)]
        audio_input_index: int | None = None
        if audio_path:
            audio_input_index = len(paths)
            cmd += [
                "-stream_loop",
                "-1",
                "-ss",
                f"{audio_start_time:.3f}",
                "-i",
                str(audio_path),
            ]

        filter_parts: list[str] = []
        for idx, duration in enumerate(durations):
            label = f"v{idx}"
            filters = (
                f"[{idx}:v]trim=0:{duration:.3f},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps={self._FPS},format=yuv420p"
            )
            filter_parts.append(f"{filters}[{label}]")

        if transition_seconds > 0:
            current_label = "v0"
            current_duration = durations[0]
            for idx in range(1, len(paths)):
                output_label = "vc" if idx == len(paths) - 1 else f"vx{idx}"
                offset = current_duration - transition_seconds
                filter_parts.append(
                    f"[{current_label}][v{idx}]xfade=transition={clean_transition}:"
                    f"duration={transition_seconds:.3f}:offset={offset:.3f}[{output_label}]"
                )
                current_label = output_label
                current_duration += durations[idx] - transition_seconds
        else:
            concat_labels = "".join(f"[v{idx}]" for idx in range(len(paths)))
            filter_parts.append(f"{concat_labels}concat=n={len(paths)}:v=1:a=0[vc]")
        if fade_out:
            filter_parts.append(f"[vc]fade=t=out:st={fade_out_start:.3f}:d={self._FADE_OUT_SECONDS}[v]")
        else:
            filter_parts.append("[vc]format=yuv420p[v]")

        if audio_input_index is not None:
            audio_filters = f"[{audio_input_index}:a]atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS,volume=0.5"
            if fade_out:
                audio_filters += f",afade=t=out:st={fade_out_start:.3f}:d={self._FADE_OUT_SECONDS}"
            filter_parts.append(f"{audio_filters}[a]")

        cmd += ["-filter_complex", ";".join(filter_parts), "-map", "[v]"]
        if audio_input_index is not None:
            cmd += ["-map", "[a]", "-c:a", "aac"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", f"{total_duration:.3f}", str(output_path)]

        subprocess.run(
            cmd,
            cwd=str(folder),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        metadata = {
            "ratio": ratio,
            "size": {"width": width, "height": height},
            "transition_seconds": transition_seconds,
            "transition_type": clean_transition,
            "duration_seconds": total_duration,
            "audio": str(audio_path) if audio_path else None,
            "audio_start_seconds": audio_start_time if audio_path else None,
            "source_videos": [str(path) for path in paths],
        }
        (folder / "montaje.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        return VideoMontageResult(
            folder=folder,
            video_path=output_path,
            source_videos=paths,
            audio_path=audio_path,
            duration_seconds=total_duration,
            ratio=ratio,
        )
