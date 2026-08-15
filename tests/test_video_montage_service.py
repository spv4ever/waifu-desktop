from __future__ import annotations

import json
from pathlib import Path

from app.services.video_montage_service import VideoMontageService


def test_plan_repeated_video_reports_original_and_total_duration(tmp_path, monkeypatch):
    source_path = tmp_path / "clip.mp4"
    source_path.write_bytes(b"video")
    service = VideoMontageService()
    monkeypatch.setattr(service, "_probe_duration", lambda path: 12.5)

    plan = service.plan_repeated_video(source_path, 4)

    assert plan.source_duration_seconds == 12.5
    assert plan.total_duration_seconds == 50.0
    assert plan.repetitions == 4


def test_repeat_video_concatenates_without_reencoding_next_to_source(tmp_path, monkeypatch):
    source_path = tmp_path / "my video.mp4"
    source_path.write_bytes(b"video")
    service = VideoMontageService()
    monkeypatch.setattr("app.services.video_montage_service.shutil.which", lambda name: "/usr/bin/ffmpeg")
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        concat_path = Path(cmd[cmd.index("-i") + 1])
        captured["concat"] = concat_path.read_text(encoding="utf-8")
        Path(cmd[-1]).write_bytes(b"repeated")

    monkeypatch.setattr("app.services.video_montage_service.subprocess.run", _fake_run)

    result = service.repeat_video(source_path, 3)

    assert result.video_path == tmp_path / "my video_long.mp4"
    assert result.repetitions == 3
    assert captured["cmd"][captured["cmd"].index("-c") + 1] == "copy"
    assert captured["concat"].count("file '") == 3
    assert not (tmp_path / ".my video_long_concat.txt").exists()


def test_repeat_video_uses_unique_output_and_requires_two_repetitions(tmp_path, monkeypatch):
    source_path = tmp_path / "clip.mp4"
    source_path.write_bytes(b"video")
    (tmp_path / "clip_long.mp4").write_bytes(b"existing")
    service = VideoMontageService()
    monkeypatch.setattr("app.services.video_montage_service.shutil.which", lambda name: "/usr/bin/ffmpeg")

    def _fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"repeated")

    monkeypatch.setattr("app.services.video_montage_service.subprocess.run", _fake_run)

    assert service.repeat_video(source_path, 2).video_path == tmp_path / "clip_long-1.mp4"

    try:
        service.repeat_video(source_path, 1)
    except ValueError as exc:
        assert "al menos 2" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


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


def test_create_montage_crossfades_overlapping_videos(tmp_path, monkeypatch):
    source_paths = [tmp_path / name for name in ("one.mp4", "two.mp4", "three.mp4")]
    for path in source_paths:
        path.write_bytes(b"video")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    service = VideoMontageService()
    monkeypatch.setattr("app.services.video_montage_service.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(service, "_probe_duration", lambda path: 4.0)
    monkeypatch.setattr(service, "_create_folder", lambda: output_dir)
    monkeypatch.setattr(service, "_select_audio_track", lambda: None)
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

    monkeypatch.setattr("app.services.video_montage_service.subprocess.run", _fake_run)

    result = service.create_montage(
        source_videos=source_paths,
        ratio="16:9",
        transition_seconds=1.0,
        transition_type="dissolve",
    )

    filter_complex = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert "xfade=transition=dissolve:duration=1.000:offset=3.000" in filter_complex
    assert "xfade=transition=dissolve:duration=1.000:offset=6.000" in filter_complex
    assert "color=c=black" not in filter_complex
    assert result.duration_seconds == 10.0
    metadata = json.loads((output_dir / "montaje.json").read_text(encoding="utf-8"))
    assert metadata["transition_type"] == "dissolve"


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
    monkeypatch.setattr("app.services.video_montage_service.random.choice", lambda items: items[0])
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

    filter_script = Path(captured["cmd"][captured["cmd"].index("-filter_complex_script") + 1])
    filter_complex = filter_script.read_text(encoding="utf-8")
    assert result.video_path == output_dir / "bulk_images_youtube_relax.mp4"
    assert result.prompt_item_ids == [1, 2]
    assert store.marked == [1, 2]
    assert "xfade=transition=fade" in filter_complex
    assert "scale=3840:2160" in filter_complex
    metadata = json.loads((output_dir / "bulk_images_youtube_relax.json").read_text(encoding="utf-8"))
    assert metadata["duration_seconds"] == 15.0
    assert metadata["audio"] == str(audio_path.resolve())
    copy_path = output_dir / "bulk_images_youtube_relax.txt"
    assert result.youtube_copy_path == copy_path
    youtube_copy = copy_path.read_text(encoding="utf-8")
    assert "TÍTULO\nrelax 🌙 Música Relajante para Desconectar" in youtube_copy
    assert "DESCRIPCIÓN\nDisfruta de relax" in youtube_copy
    assert "ETIQUETAS\nmúsica relajante, canción relajante" in youtube_copy
    assert metadata["youtube_copy"]["title"] == "relax 🌙 Música Relajante para Desconectar"
    assert metadata["youtube_copy_path"] == str(copy_path)


def test_create_bulk_images_youtube_video_writes_filter_graph_to_script(tmp_path, monkeypatch):
    """Large Bulk renders must not pass the filter graph via Windows' command line."""
    audio_dir = tmp_path / "resources" / "audio_relax"
    audio_dir.mkdir(parents=True)
    audio_path = audio_dir / "long.mp3"
    audio_path.write_bytes(b"audio")
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    class Store:
        def select_unused_bulk_images_for_youtube_video(self, *, bulk_category):
            return [
                {"id": index, "base_image_json": json.dumps({"filename": image_path.name}), "upscale_image_json": None}
                for index in range(1, 102)
            ]

        def mark_prompt_items_used_in_reel(self, prompt_item_ids):
            pass

    service = VideoMontageService()
    monkeypatch.setattr(service, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "_probe_duration", lambda path: 732.1)
    monkeypatch.setattr(service, "_create_folder", lambda: output_dir)
    monkeypatch.setattr("app.services.video_montage_service.get_store", lambda: Store())
    monkeypatch.setattr("app.services.video_montage_service.build_output_path", lambda image_json: image_path)
    monkeypatch.setattr("app.services.video_montage_service.shutil.which", lambda name: f"/usr/bin/{name}")
    captured = {}

    def _fake_render(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"rendered")

    monkeypatch.setattr(service, "_run_ffmpeg_render", _fake_render)

    service.create_bulk_images_youtube_video(
        bulk_category="Nature Wallpaper",
        audio_filename=audio_path.name,
    )

    assert "-filter_complex" not in captured["cmd"]
    script_path = Path(captured["cmd"][captured["cmd"].index("-filter_complex_script") + 1])
    assert script_path == output_dir / "bulk_images_youtube_long_filters.txt"
    filter_graph = script_path.read_text(encoding="utf-8")
    assert "[100:v]scale=3840:2160" in filter_graph
    assert "[xf99][v100]xfade=" in filter_graph


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


def test_create_bulk_images_youtube_video_joins_two_tracks_before_rendering(tmp_path, monkeypatch):
    audio_dir = tmp_path / "resources" / "audio_relax"
    audio_dir.mkdir(parents=True)
    first_audio = audio_dir / "rain.mp3"
    second_audio = audio_dir / "forest.mp3"
    first_audio.write_bytes(b"first")
    second_audio.write_bytes(b"second")
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    class Store:
        def select_unused_bulk_images_for_youtube_video(self, *, bulk_category):
            return [
                {"id": index, "base_image_json": json.dumps({"filename": image_path.name}), "upscale_image_json": None}
                for index in range(1, 4)
            ]

        def mark_prompt_items_used_in_reel(self, prompt_item_ids):
            self.marked = list(prompt_item_ids)

    service = VideoMontageService()
    monkeypatch.setattr(service, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "_probe_duration", lambda path: 5.0 if path == first_audio else 7.0)
    monkeypatch.setattr(service, "_create_folder", lambda: output_dir)
    monkeypatch.setattr("app.services.video_montage_service.get_store", lambda: Store())
    monkeypatch.setattr("app.services.video_montage_service.build_output_path", lambda image_json: image_path)
    monkeypatch.setattr("app.services.video_montage_service.shutil.which", lambda name: f"/usr/bin/{name}")
    commands = []

    def _fake_run(cmd, **kwargs):
        commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"rendered")

    monkeypatch.setattr("app.services.video_montage_service.subprocess.run", _fake_run)

    result = service.create_bulk_images_youtube_video(
        bulk_category="Nature Wallpaper",
        audio_filename=first_audio.name,
        second_audio_filename=second_audio.name,
    )

    merged_audio = output_dir / "tema_final_rain_forest.mp3"
    assert commands[0][-1] == str(merged_audio)
    merge_filter = commands[0][commands[0].index("-filter_complex") + 1]
    assert "[a0][a1]concat=n=2:v=0:a=1[a]" in merge_filter
    assert str(merged_audio) in commands[1]
    assert result.audio_path == merged_audio
    assert result.duration_seconds == 12.0
    metadata = json.loads((output_dir / "bulk_images_youtube_rain_forest.json").read_text(encoding="utf-8"))
    assert metadata["source_audios"] == [str(first_audio), str(second_audio)]
