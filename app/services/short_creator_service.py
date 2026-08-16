from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ShortClip:
    number: int
    start_seconds: float
    duration_seconds: float
    video_path: Path
    copy_path: Path
    posts: tuple[str, ...]


@dataclass(frozen=True)
class ShortCreationResult:
    folder: Path
    source_path: Path
    source_duration_seconds: float
    clips: tuple[ShortClip, ...]
    manifest_path: Path


class ShortCreatorService:
    """Corta un vídeo horizontal en Shorts verticales mediante recorte central."""

    _VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

    def _output_root(self) -> Path:
        root = Path(__file__).resolve().parents[2] / "outputs" / "youtube_shorts"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _create_folder(self, source: Path) -> Path:
        safe_stem = re.sub(r"[^\w.-]+", "_", source.stem, flags=re.UNICODE).strip("_.") or "video"
        base = self._output_root() / f"{datetime.now():%Y%m%d_%H%M%S}_{safe_stem}"
        folder = base
        suffix = 2
        while folder.exists():
            folder = Path(f"{base}_{suffix}")
            suffix += 1
        folder.mkdir(parents=True)
        return folder

    def _probe(self, path: Path) -> tuple[float, int, int]:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise RuntimeError("No se encontró ffprobe. Instala FFmpeg y añádelo al PATH.")
        completed = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        payload = json.loads(completed.stdout)
        streams = payload.get("streams") or []
        if not streams:
            raise ValueError("El fichero no contiene una pista de vídeo.")
        return float(payload["format"]["duration"]), int(streams[0]["width"]), int(streams[0]["height"])

    @staticmethod
    def _post_variants(song_title: str, youtube_url: str, part: int) -> tuple[str, ...]:
        link = f"\n🎬 Vídeo completo: {youtube_url}" if youtube_url else ""
        return (
            f"🎵 {song_title} — parte {part}. Un instante para desconectar.{link}\n#Shorts #Música",
            f"¿Te acompaña este fragmento de «{song_title}»? ✨{link}\n#YouTubeShorts #Relax",
            f"Un minuto de calma con {song_title} 🌙{link}\n#Shorts #MusicaRelajante",
        )

    def create_shorts(
        self,
        source_video: str | Path,
        *,
        clip_seconds: float,
        clip_count: int,
        song_title: str,
        youtube_url: str = "",
        progress_callback: Callable[[str], None] | None = None,
    ) -> ShortCreationResult:
        source = Path(source_video).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in self._VIDEO_EXTENSIONS:
            raise ValueError("Selecciona un fichero de vídeo compatible.")
        if clip_seconds <= 0 or clip_count <= 0:
            raise ValueError("La duración y el número de Shorts deben ser mayores que cero.")
        song_title = song_title.strip() or source.stem
        duration, width, height = self._probe(source)
        if width <= height or abs((width / height) - (16 / 9)) > 0.08:
            raise ValueError(f"Se esperaba un vídeo 16:9 horizontal; se detectó {width}x{height}.")
        available = math.ceil(duration / clip_seconds)
        total = min(clip_count, available)
        if total < 1:
            raise ValueError("El vídeo no tiene duración suficiente para crear Shorts.")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("No se encontró ffmpeg. Instala FFmpeg y añádelo al PATH.")

        folder = self._create_folder(source)
        clips: list[ShortClip] = []
        # No hay scale: se conserva cada píxel y solo se toma una ventana 9:16 centrada.
        crop_filter = "crop=trunc(ih*9/16/2)*2:trunc(ih/2)*2:(iw-ow)/2:(ih-oh)/2,setsar=1"
        try:
            for index in range(total):
                start = index * clip_seconds
                actual_duration = min(clip_seconds, duration - start)
                number = index + 1
                video_path = folder / f"short_{number:02d}.mp4"
                if progress_callback:
                    progress_callback(f"Creando Short {number} de {total}…")
                subprocess.run(
                    [
                        ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", str(source),
                        "-t", f"{actual_duration:.3f}", "-map", "0:v:0", "-map", "0:a?",
                        "-vf", crop_filter, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(video_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                posts = self._post_variants(song_title, youtube_url.strip(), number)
                copy_path = folder / f"short_{number:02d}_posts.txt"
                copy_path.write_text(
                    "\n\n".join(f"POST {post_index}\n{post}" for post_index, post in enumerate(posts, 1)) + "\n",
                    encoding="utf-8",
                )
                clips.append(ShortClip(number, start, actual_duration, video_path, copy_path, posts))

            manifest_path = folder / "shorts.json"
            manifest = {
                "source_path": str(source),
                "source_duration_seconds": duration,
                "song_title": song_title,
                "youtube_url": youtube_url.strip(),
                "crop": "9:16 vertical centrado, sin escalado",
                "clips": [
                    {**asdict(clip), "video_path": str(clip.video_path), "copy_path": str(clip.copy_path)}
                    for clip in clips
                ],
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return ShortCreationResult(folder, source, duration, tuple(clips), manifest_path)
