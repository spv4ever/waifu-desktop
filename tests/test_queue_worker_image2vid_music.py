from __future__ import annotations

from pathlib import Path

from app.services.queue_worker import QueueWorker


class _Logger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


def _build_worker() -> tuple[QueueWorker, _Logger]:
    logger = _Logger()
    worker = QueueWorker.__new__(QueueWorker)
    worker._log_callback = logger
    return worker, logger


def test_add_reel_music_returns_original_if_ffmpeg_missing(tmp_path, monkeypatch):
    worker, logger = _build_worker()
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")

    monkeypatch.setattr("app.services.queue_worker.shutil.which", lambda name: None)

    result = worker._add_reel_music_to_image2vid(video_path=video_path)

    assert result == video_path
    assert any("ffmpeg no disponible" in msg for msg in logger.messages)


def test_add_reel_music_returns_original_if_no_audio_available(tmp_path, monkeypatch):
    worker, _ = _build_worker()
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")

    def _fake_which(name: str) -> str | None:
        if name == "ffmpeg":
            return "/usr/bin/ffmpeg"
        return None

    monkeypatch.setattr("app.services.queue_worker.shutil.which", _fake_which)
    monkeypatch.setattr(worker, "_probe_video_duration", lambda **kwargs: 3.5)
    monkeypatch.setattr(worker, "_pick_reel_audio_for_duration", lambda **kwargs: None)

    result = worker._add_reel_music_to_image2vid(video_path=video_path)

    assert result == video_path


def test_add_reel_music_creates_new_file_when_ffmpeg_succeeds(tmp_path, monkeypatch):
    worker, logger = _build_worker()
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video")

    def _fake_which(name: str) -> str | None:
        if name == "ffmpeg":
            return "/usr/bin/ffmpeg"
        return None

    monkeypatch.setattr("app.services.queue_worker.shutil.which", _fake_which)
    monkeypatch.setattr(worker, "_probe_video_duration", lambda **kwargs: 4.0)

    audio_path = tmp_path / "track.mp3"
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(
        worker,
        "_pick_reel_audio_for_duration",
        lambda **kwargs: (audio_path, 0.4, True),
    )

    def _fake_run(cmd, check, capture_output, text):
        out_path = Path(cmd[-1])
        out_path.write_bytes(b"rendered")

    monkeypatch.setattr("app.services.queue_worker.subprocess.run", _fake_run)

    result = worker._add_reel_music_to_image2vid(video_path=video_path)

    assert result.name == "sample_music.mp4"
    assert result.exists()
    assert any("Image2Vid con música aplicada" in msg for msg in logger.messages)
