from pathlib import Path

from app.services.video_preview import resolve_video_preview_url


def test_video_preview_prefers_saved_local_video(tmp_path, monkeypatch):
    video_path = tmp_path / "rendered video.mp4"
    video_path.write_bytes(b"video")
    monkeypatch.setattr("app.services.video_preview.build_output_path", lambda *args, **kwargs: video_path)

    result = resolve_video_preview_url(
        row={"meta_json": "{}"},
        video={"filename": video_path.name},
    )

    assert result == video_path.resolve().as_uri()


def test_video_preview_does_not_use_remote_url_when_local_video_is_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.video_preview.build_output_path",
        lambda *args, **kwargs: Path("missing-video.mp4"),
    )

    result = resolve_video_preview_url(
        row={"meta_json": "{}"},
        video={"filename": "missing-video.mp4"},
    )

    assert result is None
