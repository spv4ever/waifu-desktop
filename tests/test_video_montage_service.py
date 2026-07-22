from __future__ import annotations

import json
from pathlib import Path

from app.services.video_montage_service import VideoMontageService


def test_select_audio_track_starts_randomly_within_first_minute(tmp_path, monkeypatch):
    audio_dir = tmp_path / "resources" / "audio"
    audio_dir.mkdir(parents=True)
    audio_path = audio_dir / "track.mp3"
    audio_path.write_bytes(b"audio")

    service = VideoMontageService()
    monkeypatch.setattr(service, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "_probe_duration", lambda path: 180.0)
    monkeypatch.setattr("app.services.video_montage_service.random.choice", lambda items: items[0])
    monkeypatch.setattr("app.services.video_montage_service.random.uniform", lambda start, end: end)

    assert service._select_audio_track() == (audio_path, 60.0)


def test_create_montage_seeks_audio_before_input_and_records_offset(tmp_path, monkeypatch):
    source_paths = [tmp_path / "one.mp4", tmp_path / "two.mp4"]
    for path in source_paths:
        path.write_bytes(b"video")
    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"audio")
    output_dir = tmp_path / "output"

    service = VideoMontageService()
    monkeypatch.setattr(
        "app.services.video_montage_service.shutil.which",
        lambda name: f"/usr/bin/{name}",
    )
    monkeypatch.setattr(service, "_probe_duration", lambda path: 2.0)
    monkeypatch.setattr(service, "_create_folder", lambda: output_dir)
    monkeypatch.setattr(service, "_select_audio_track", lambda: (audio_path, 37.25))
    output_dir.mkdir()

    captured: dict[str, list[str]] = {}

    def _fake_run(cmd, cwd, check, capture_output, text, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"rendered")

    monkeypatch.setattr("app.services.video_montage_service.subprocess.run", _fake_run)

    result = service.create_montage(source_videos=source_paths, ratio="9:16")

    assert result.video_path == output_dir / "montaje.mp4"
    audio_path_index = captured["cmd"].index(str(audio_path))
    assert captured["cmd"][audio_path_index - 3 : audio_path_index - 1] == [
        "-ss",
        "37.250",
    ]
    metadata = json.loads((output_dir / "montaje.json").read_text(encoding="utf-8"))
    assert metadata["audio_start_seconds"] == 37.25


def test_create_bulk_images_youtube_video_uses_full_audio_and_marks_images(tmp_path, monkeypatch):
    audio_dir = tmp_path / "resources" / "audio_relax"
    audio_dir.mkdir(parents=True)
    audio_path = audio_dir / "relax.mp3"
    audio_path.write_bytes(b"audio")
    image_paths = []
    for idx in range(3):
        path = tmp_path / f"image_{idx}.png"
        path.write_bytes(b"image")
        image_paths.append(path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    class Store:
        def __init__(self):
            self.marked = []

        def select_unused_bulk_images_for_youtube_video(self, *, bulk_category):
            assert bulk_category == "Nature Wallpaper"
            return [
                {"id": idx + 1, "base_image_json": json.dumps({"filename": path.name}), "upscale_image_json": None}
                for idx, path in enumerate(image_paths)
            ]

        def mark_prompt_items_used_in_reel(self, prompt_item_ids):
            self.marked = list(prompt_item_ids)

    store = Store()
    service = VideoMontageService()
    monkeypatch.setattr(service, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "_probe_duration", lambda path: 15.0)
    monkeypatch.setattr(service, "_create_folder", lambda: output_dir)
    monkeypatch.setattr("app.services.video_montage_service.get_store", lambda: store)
    monkeypatch.setattr(
        "app.services.video_montage_service.build_output_path",
        lambda image_json: tmp_path / image_json["filename"],
    )
    monkeypatch.setattr("app.services.video_montage_service.random.shuffle", lambda items: None)
    monkeypatch.setattr("app.services.video_montage_service.shutil.which", lambda name: f"/usr/bin/{name}")

    captured = {}

    def _fake_run(cmd, cwd, check, capture_output, text, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"rendered")

    monkeypatch.setattr("app.services.video_montage_service.subprocess.run", _fake_run)

    result = service.create_bulk_images_youtube_video(
        bulk_category="Nature Wallpaper",
        audio_filename="relax.mp3",
        image_display_seconds=8.0,
        transition_seconds=0.75,
    )

    filter_complex = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert result.video_path == output_dir / "bulk_images_youtube_relax.mp4"
    assert result.prompt_item_ids == [1, 2]
    assert store.marked == [1, 2]
    assert "xfade=transition=fade" in filter_complex
    assert "scale=3840:2160" in filter_complex
    metadata = json.loads((output_dir / "bulk_images_youtube_relax.json").read_text(encoding="utf-8"))
    assert metadata["duration_seconds"] == 15.0
    assert metadata["audio"] == str(audio_path.resolve())

def test_create_bulk_images_youtube_video_reports_progress(tmp_path, monkeypatch):
    audio_dir = tmp_path / "resources" / "audio_relax"
    audio_dir.mkdir(parents=True)
    audio_path = audio_dir / "relax.mp3"
    audio_path.write_bytes(b"audio")
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    class Store:
        def select_unused_bulk_images_for_youtube_video(self, *, bulk_category):
            return [{"id": 1, "base_image_json": json.dumps({"filename": image_path.name}), "upscale_image_json": None}]

        def mark_prompt_items_used_in_reel(self, prompt_item_ids):
            self.marked = list(prompt_item_ids)

    service = VideoMontageService()
    store = Store()
    events = []
    monkeypatch.setattr(service, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "_probe_duration", lambda path: 5.0)
    monkeypatch.setattr(service, "_create_folder", lambda: output_dir)
    monkeypatch.setattr("app.services.video_montage_service.get_store", lambda: store)
    monkeypatch.setattr("app.services.video_montage_service.build_output_path", lambda image_json: tmp_path / image_json["filename"])
    monkeypatch.setattr("app.services.video_montage_service.shutil.which", lambda name: f"/usr/bin/{name}")

    def _fake_render(cmd, *, cwd, total_seconds, progress_callback=None):
        Path(cmd[-1]).write_bytes(b"rendered")
        assert total_seconds == 5.0
        progress_callback("Renderizando: 100% (5.0s/5.0s) · ETA 0s")

    monkeypatch.setattr(service, "_run_ffmpeg_render", _fake_render)

    service.create_bulk_images_youtube_video(
        bulk_category="Nature Wallpaper",
        audio_filename=audio_path.name,
        progress_callback=events.append,
    )

    assert events[0] == "Validando audio seleccionado..."
    assert any("Seleccionando" in event for event in events)
    assert any("ETA" in event for event in events)
    assert events[-1].startswith("Vídeo creado correctamente:")
