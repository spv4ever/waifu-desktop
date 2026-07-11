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

    def _fake_run(cmd, cwd, check, capture_output, text):
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
