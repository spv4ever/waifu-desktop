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


def test_upload_waifu_to_cloudinary_uploads_every_image(monkeypatch) -> None:
    worker = QueueWorker.__new__(QueueWorker)
    worker.store = _Store()
    worker._log_callback = _Logger()

    images = [
        {"filename": "waifu_1.png", "subfolder": "batch", "type": "output"},
        {"filename": "waifu_2.png", "subfolder": "batch", "type": "output"},
        {"filename": "waifu_3.png", "subfolder": "batch", "type": "output"},
    ]
    uploaded_paths: list[str] = []

    def fake_build_output_path(image_json, *, workflow_key=None):
        return f"/outputs/{workflow_key}/{image_json['filename']}"

    def fake_upload_waifu_image(*, image_path, title, checkpoint, version, created_at):
        uploaded_paths.append(str(image_path))
        index = len(uploaded_paths)
        return {"secure_url": f"https://waifu-cdn.example/{index}.png", "public_id": f"waifu-public-{index}"}

    monkeypatch.setattr("app.services.queue_worker.build_output_path", fake_build_output_path)
    monkeypatch.setattr("app.services.queue_worker.upload_waifu_image", fake_upload_waifu_image)

    worker._upload_waifu_to_cloudinary(
        prompt_item_id=20,
        meta={"workflow": "waifu", "created_at": "2026-06-21T00:00:00"},
        checkpoint_base="checkpoint.safetensors",
        image_jsons=images,
        title="Waifu Batch",
    )

    assert uploaded_paths == [
        "/outputs/waifu/waifu_1.png",
        "/outputs/waifu/waifu_2.png",
        "/outputs/waifu/waifu_3.png",
    ]
    assert worker.store.updates == {
        "waifu_cloudinary_url": "https://waifu-cdn.example/1.png",
        "waifu_cloudinary_public_id": "waifu-public-1",
        "waifu_cloudinary_uploaded_at": worker.store.updates["waifu_cloudinary_uploaded_at"],
        "waifu_cloudinary_images": [
            {"url": "https://waifu-cdn.example/1.png", "public_id": "waifu-public-1", "image_json": images[0]},
            {"url": "https://waifu-cdn.example/2.png", "public_id": "waifu-public-2", "image_json": images[1]},
            {"url": "https://waifu-cdn.example/3.png", "public_id": "waifu-public-3", "image_json": images[2]},
        ],
    }
