from __future__ import annotations

from app.services.queue_worker import QueueWorker


class _Store:
    def __init__(self) -> None:
        self.updates: dict[str, object] | None = None

    def update_prompt_item_meta(self, *, prompt_id: int, updates: dict[str, object]) -> None:
        self.updates = updates


class _Logger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


def test_upload_anime_to_cloudinary_uploads_every_image(monkeypatch) -> None:
    worker = QueueWorker.__new__(QueueWorker)
    worker.store = _Store()
    worker._log_callback = _Logger()

    images = [
        {"filename": "anime_1.png", "subfolder": "batch", "type": "output"},
        {"filename": "anime_2.png", "subfolder": "batch", "type": "output"},
        {"filename": "anime_3.png", "subfolder": "batch", "type": "output"},
    ]
    uploaded_paths: list[str] = []
    uploaded_versions: list[str | None] = []

    def fake_build_output_path(image_json, *, workflow_key=None):
        return f"/outputs/{workflow_key}/{image_json['filename']}"

    def fake_upload_anime_image(*, image_path, title, checkpoint, version, created_at):
        uploaded_paths.append(str(image_path))
        uploaded_versions.append(version)
        index = len(uploaded_paths)
        return {"secure_url": f"https://anime-cdn.example/{index}.png", "public_id": f"anime-public-{index}"}

    monkeypatch.setattr("app.services.queue_worker.build_output_path", fake_build_output_path)
    monkeypatch.setattr("app.services.queue_worker.upload_anime_image", fake_upload_anime_image)

    worker._upload_anime_to_cloudinary(
        prompt_item_id=30,
        meta={"workflow": "anime_v5", "created_at": "2026-06-21T00:00:00", "anime_v5_content_rating": "nsfw"},
        checkpoint_base="checkpoint.safetensors",
        image_jsons=images,
        title="Anime Batch",
    )

    assert uploaded_paths == [
        "/outputs/anime_v5/anime_1.png",
        "/outputs/anime_v5/anime_2.png",
        "/outputs/anime_v5/anime_3.png",
    ]
    assert uploaded_versions == ["anime nsfw", "anime nsfw", "anime nsfw"]
    assert worker.store.updates == {
        "anime_cloudinary_url": "https://anime-cdn.example/1.png",
        "anime_cloudinary_public_id": "anime-public-1",
        "anime_cloudinary_uploaded_at": worker.store.updates["anime_cloudinary_uploaded_at"],
        "anime_cloudinary_images": [
            {"url": "https://anime-cdn.example/1.png", "public_id": "anime-public-1", "image_json": images[0]},
            {"url": "https://anime-cdn.example/2.png", "public_id": "anime-public-2", "image_json": images[1]},
            {"url": "https://anime-cdn.example/3.png", "public_id": "anime-public-3", "image_json": images[2]},
        ],
    }
