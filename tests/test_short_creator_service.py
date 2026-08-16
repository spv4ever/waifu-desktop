from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.short_creator_service import ShortCreatorService


def test_create_shorts_center_crops_without_scaling_and_keeps_timeline_audio(tmp_path, monkeypatch):
    source = tmp_path / "long song.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "shorts"
    service = ShortCreatorService()
    monkeypatch.setattr(service, "_probe", lambda path: (125.0, 1920, 1080))
    monkeypatch.setattr(service, "_create_folder", lambda path: output)
    monkeypatch.setattr("app.services.short_creator_service.shutil.which", lambda name: f"/bin/{name}")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"short")

    monkeypatch.setattr("app.services.short_creator_service.subprocess.run", fake_run)
    output.mkdir()

    result = service.create_shorts(
        source,
        clip_seconds=60,
        clip_count=4,
        song_title="Moon Song",
        youtube_url="https://youtu.be/original",
    )

    assert len(result.clips) == 3
    assert [clip.duration_seconds for clip in result.clips] == [60, 60, 5]
    assert [command[command.index("-ss") + 1] for command in commands] == ["0.000", "60.000", "120.000"]
    assert all("scale=" not in command[command.index("-vf") + 1] for command in commands)
    assert all("crop=trunc(ih*9/16/2)*2" in command[command.index("-vf") + 1] for command in commands)
    assert all(command[command.index("-map") + 1] == "0:v:0" for command in commands)
    assert all("0:a?" in command for command in commands)
    assert "Moon Song" in result.clips[0].copy_path.read_text(encoding="utf-8")
    assert "https://youtu.be/original" in result.clips[0].copy_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["crop"] == "9:16 vertical centrado, sin escalado"


def test_create_shorts_rejects_non_horizontal_16_9_video(tmp_path, monkeypatch):
    source = tmp_path / "vertical.mp4"
    source.write_bytes(b"video")
    service = ShortCreatorService()
    monkeypatch.setattr(service, "_probe", lambda path: (30.0, 1080, 1920))

    with pytest.raises(ValueError, match="16:9 horizontal"):
        service.create_shorts(source, clip_seconds=15, clip_count=2, song_title="Song")
