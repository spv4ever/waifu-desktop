from __future__ import annotations

from app.services import reel_service
from app.services.reel_service import ReelService


class _AnimeV5ReelStore:
    def __init__(self) -> None:
        self.include_nsfw: bool | None = None

    def select_unused_anime_v5_reel_images(self, *, list_name, character, include_nsfw=True):
        self.include_nsfw = include_nsfw
        return [
            {
                "id": 7,
                "base_image_json": '{"filename": "sfw.png", "subfolder": "", "type": "output"}',
                "upscale_image_json": None,
            }
        ]


def test_anime_v5_reel_selection_can_exclude_nsfw(monkeypatch, tmp_path) -> None:
    store = _AnimeV5ReelStore()
    image_path = tmp_path / "sfw.png"
    image_path.write_text("image", encoding="utf-8")

    monkeypatch.setattr(reel_service, "get_store", lambda: store)
    monkeypatch.setattr(reel_service, "build_output_path", lambda image_json, *, workflow_key=None: image_path)

    images = ReelService()._select_unused_anime_v5_images(
        list_name="One Piece",
        character="Nami",
        image_count=1,
        include_nsfw=False,
    )

    assert store.include_nsfw is False
    assert [image.prompt_item_id for image in images] == [7]
