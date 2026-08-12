from __future__ import annotations

from pathlib import Path

import pytest

from app.services.x_media_service import XMediaService


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
        "",
        "https://example.com/status/123",
        "https://x.com/example",
        "https://youtube.com/watch",
        "https://youtube.com/shorts/",
        "https://youtu.be/",
        "file:///tmp/video.mp4",
    ],
)
def test_validate_url_rejects_non_post_links(url: str) -> None:
    with pytest.raises(ValueError):
        XMediaService.validate_url(url)


def test_media_type_recognizes_video_and_images() -> None:
    assert XMediaService._media_type(Path("clip.mp4")) == "video"
    assert XMediaService._media_type(Path("photo.jpg")) == "image"
