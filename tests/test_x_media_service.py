from __future__ import annotations

from pathlib import Path

import pytest

from app.services.x_media_service import SocialMediaDownloadError, XMediaService


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/example/status/123",
        "https://www.x.com/example/status/123?s=20",
        "https://twitter.com/example/status/123",
    ],
)
def test_validate_url_accepts_x_status_links(url: str) -> None:
    assert XMediaService.validate_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtube.com/shorts/abc123",
        "https://m.youtube.com/shorts/abc123?feature=share",
        "https://youtu.be/abc123",
    ],
)
def test_validate_url_accepts_youtube_video_and_shorts_links(url: str) -> None:
    assert XMediaService.validate_url(url) == url
    assert XMediaService.platform_for_url(url) == "youtube"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/p/ABC123/",
        "https://instagram.com/reel/ABC123/?igsh=example",
        "https://m.instagram.com/reels/ABC123/",
        "https://instagram.com/tv/ABC123/",
    ],
)
def test_validate_url_accepts_instagram_posts_and_reels(url: str) -> None:
    assert XMediaService.validate_url(url) == url
    assert XMediaService.platform_for_url(url) == "instagram"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@creator/video/1234567890",
        "https://m.tiktok.com/@creator/photo/1234567890?is_from_webapp=1",
        "https://vm.tiktok.com/ZMexample/",
        "https://vt.tiktok.com/ZSexample/",
        "https://www.tiktok.com/t/ZTexample/",
    ],
)
def test_validate_url_accepts_tiktok_posts_and_short_links(url: str) -> None:
    assert XMediaService.validate_url(url) == url
    assert XMediaService.platform_for_url(url) == "tiktok"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/status/123",
        "https://x.com/example",
        "https://youtube.com/watch",
        "https://youtube.com/shorts/",
        "https://youtu.be/",
        "https://instagram.com/example/",
        "https://instagram.com/reel/",
        "https://tiktok.com/@creator",
        "https://tiktok.com/@creator/video/",
        "https://vm.tiktok.com/",
        "file:///tmp/video.mp4",
    ],
)
def test_validate_url_rejects_non_post_links(url: str) -> None:
    with pytest.raises(ValueError):
        XMediaService.validate_url(url)


def test_media_type_recognizes_video_and_images() -> None:
    assert XMediaService._media_type(Path("clip.mp4")) == "video"
    assert XMediaService._media_type(Path("photo.jpg")) == "image"


def test_x_status_id_is_extracted_from_url() -> None:
    url = "https://x.com/example/status/2089055730645307814?s=20"
    assert XMediaService._x_status_id(url) == "2089055730645307814"


def test_x_video_url_is_canonicalized_for_extractors() -> None:
    url = "https://x.com/_Enjoysex/status/2088536024322634228/video/1?ref_src=test"
    assert XMediaService._canonical_x_url(url) == (
        "https://x.com/_Enjoysex/status/2088536024322634228"
    )


def test_configured_x_cookie_browser_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.x_media_service.settings",
        type("Settings", (), {"x_cookies_browser": "edge"})(),
    )
    assert XMediaService._x_cookie_browsers() == ["edge"]


def test_x_cookie_browser_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.x_media_service.settings",
        type("Settings", (), {"x_cookies_browser": "off"})(),
    )
    assert XMediaService._x_cookie_browsers() == []


def test_clean_error_removes_ansi_codes() -> None:
    error = "\x1b[0;31mERROR:\x1b[0m [twitter] No video could be found"
    assert XMediaService._clean_error(error) == "ERROR: [twitter] No video could be found"


def test_gallery_fallback_collects_downloaded_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> object:
        assert command[-1] == "https://x.com/example/status/123"
        (tmp_path / "photo_1.jpg").write_bytes(b"image")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("app.services.x_media_service.subprocess.run", fake_run)

    assert XMediaService._download_x_gallery(
        "https://x.com/example/status/123", tmp_path
    ) == [(tmp_path / "photo_1.jpg").resolve()]


def test_gallery_fallback_reports_clean_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = type(
        "Result",
        (),
        {"returncode": 1, "stdout": "", "stderr": "\x1b[31mAuthenticationError\x1b[0m"},
    )()
    monkeypatch.setattr(
        "app.services.x_media_service.subprocess.run",
        lambda *_args, **_kwargs: result,
    )

    with pytest.raises(SocialMediaDownloadError, match="AuthenticationError"):
        XMediaService._download_x_gallery("https://x.com/example/status/123", tmp_path)
