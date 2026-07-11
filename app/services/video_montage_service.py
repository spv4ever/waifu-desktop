from __future__ import annotations

import json
import random
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class VideoMontageResult:
    folder: Path
    video_path: Path
    source_videos: list[Path]
    audio_path: Path | None
    duration_seconds: float
    ratio: str


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

    def create_montage(
        self,
        *,
        source_videos: list[str | Path],
        ratio: str,
        transition_seconds: float | None = None,
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
        width, height = self._RATIO_SIZES[ratio]
        durations = [self._probe_duration(path) for path in paths]
        total_duration = sum(durations) + (transition_seconds * max(len(paths) - 1, 0))
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
        concat_labels: list[str] = []
        for idx, duration in enumerate(durations):
            label = f"v{idx}"
            filters = (
                f"[{idx}:v]trim=0:{duration:.3f},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps={self._FPS},format=yuv420p"
            )
            if transition_seconds > 0:
                if idx > 0:
                    filters += f",fade=t=in:st=0:d={min(transition_seconds, duration / 2):.3f}"
                if idx < len(paths) - 1:
                    fade_start = max(duration - min(transition_seconds, duration / 2), 0.0)
                    filters += f",fade=t=out:st={fade_start:.3f}:d={min(transition_seconds, duration / 2):.3f}"
            filter_parts.append(f"{filters}[{label}]")
            concat_labels.append(f"[{label}]")
            if idx < len(paths) - 1 and transition_seconds > 0:
                black_label = f"bt{idx}"
                filter_parts.append(f"color=c=black:s={width}x{height}:d={transition_seconds:.3f}:r={self._FPS},format=yuv420p[{black_label}]")
                concat_labels.append(f"[{black_label}]")

        segment_count = len(concat_labels)
        filter_parts.append(f"{''.join(concat_labels)}concat=n={segment_count}:v=1:a=0[vc]")
        if fade_out:
            filter_parts.append(f"[vc]fade=t=out:st={fade_out_start:.3f}:d={self._FADE_OUT_SECONDS}[v]")
        else:
            filter_parts.append("[vc]format=yuv420p[v]")

        if audio_input_index is not None:
            filter_parts.append(
                f"[{audio_input_index}:a]atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS,volume=0.5,"
                f"afade=t=out:st={fade_out_start:.3f}:d={self._FADE_OUT_SECONDS}[a]"
            )

        cmd += ["-filter_complex", ";".join(filter_parts), "-map", "[v]"]
        if audio_input_index is not None:
            cmd += ["-map", "[a]", "-c:a", "aac"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-t", f"{total_duration:.3f}", str(output_path)]

        subprocess.run(cmd, cwd=str(folder), check=True, capture_output=True, text=True)

        metadata = {
            "ratio": ratio,
            "size": {"width": width, "height": height},
            "transition_seconds": transition_seconds,
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
