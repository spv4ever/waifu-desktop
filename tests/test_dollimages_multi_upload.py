from __future__ import annotations

from app.services.comfy_history_parser import extract_base_and_upscale, extract_base_and_upscale_images
from app.services.queue_worker import QueueWorker, _select_dollimages_upload_images


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


def test_extract_base_and_upscale_images_keeps_all_images() -> None:
    entry = {
        "outputs": {
            "9": {
                "images": [
                    {"filename": "img_1.png", "subfolder": "batch", "type": "output"},
                    {"filename": "img_2.png", "subfolder": "batch", "type": "output"},
                    {"filename": "img_3.png", "subfolder": "batch", "type": "output"},
                ]
            }
        }
    }

    base_images, up_images = extract_base_and_upscale_images(entry, workflow_key="dollimagesz")
    base_image, up_image = extract_base_and_upscale(entry, workflow_key="dollimagesz")

    assert [image["filename"] for image in base_images] == ["img_1.png", "img_2.png", "img_3.png"]
    assert up_images == []
    assert base_image == base_images[0]
    assert up_image is None


def test_upload_dollimages_to_cloudinary_uploads_every_image(monkeypatch) -> None:
    worker = QueueWorker.__new__(QueueWorker)
    worker.store = _Store()
    worker._log_callback = _Logger()

    images = [
        {"filename": "img_1.png", "subfolder": "batch", "type": "output"},
        {"filename": "img_2.png", "subfolder": "batch", "type": "output"},
        {"filename": "img_3.png", "subfolder": "batch", "type": "output"},
    ]
    uploaded_paths: list[str] = []

    def fake_build_output_path(image_json, *, workflow_key=None):
        return f"/outputs/{workflow_key}/{image_json['filename']}"

    def fake_upload_dollimages_image(*, image_path, title, checkpoint, version, created_at):
        uploaded_paths.append(str(image_path))
        index = len(uploaded_paths)
        return {"secure_url": f"https://cdn.example/{index}.png", "public_id": f"public-{index}"}

    monkeypatch.setattr("app.services.queue_worker.build_output_path", fake_build_output_path)
    monkeypatch.setattr("app.services.queue_worker.upload_dollimages_image", fake_upload_dollimages_image)

    worker._upload_dollimages_to_cloudinary(
        prompt_item_id=10,
        meta={"workflow": "dollimagesz", "created_at": "2026-06-21T00:00:00"},
        checkpoint_base="checkpoint.safetensors",
        image_jsons=images,
        title="Batch",
    )

    assert uploaded_paths == [
        "/outputs/dollimagesz/img_1.png",
        "/outputs/dollimagesz/img_2.png",
        "/outputs/dollimagesz/img_3.png",
    ]
    assert worker.store.updates == {
        "cloudinary_url": "https://cdn.example/1.png",
        "cloudinary_public_id": "public-1",
        "cloudinary_uploaded_at": worker.store.updates["cloudinary_uploaded_at"],
        "cloudinary_images": [
            {"url": "https://cdn.example/1.png", "public_id": "public-1", "image_json": images[0]},
            {"url": "https://cdn.example/2.png", "public_id": "public-2", "image_json": images[1]},
            {"url": "https://cdn.example/3.png", "public_id": "public-3", "image_json": images[2]},
        ],
    }


def test_select_dollimages_upload_images_prefers_complete_upscale_batch() -> None:
    base_images = [{"filename": "base_1.png", "subfolder": "batch", "type": "output"}]
    up_images = [
        {"filename": "up_1.png", "subfolder": "batch", "type": "output"},
        {"filename": "up_2.png", "subfolder": "batch", "type": "output"},
        {"filename": "up_3.png", "subfolder": "batch", "type": "output"},
    ]

    assert _select_dollimages_upload_images(
        base_images=base_images,
        up_images=up_images,
        base_img=base_images[0],
        up_img=up_images[0],
    ) == up_images
