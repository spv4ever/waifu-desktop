from app.domain.models import ImageToVideoCreate
from app.services.image2vid_service import ImageToVideoService


class _Store:
    def __init__(self) -> None:
        self.prompt_meta = None

    def create_pack(self, **kwargs) -> int:
        return 1

    def try_register_combo(self, **kwargs) -> bool:
        return True

    def create_prompt_item(self, **kwargs) -> int:
        self.prompt_meta = kwargs["meta"]
        return 2

    def create_queue_job(self, **kwargs) -> int:
        return 3


def test_undress_meta_uses_undress_category() -> None:
    store = _Store()
    service = ImageToVideoService.__new__(ImageToVideoService)
    service.store = store
    service._prepare_source_image = lambda source_path: "source.png"

    request = ImageToVideoCreate(
        source_category="waifu",
        source_prompt_id=10,
        source_url="",
        source_image="source.jpg",
        title="Undress waifu #10",
        prompt_text="prompt",
        negative_text="negative",
        ratio="5:8",
        width=480,
        height=768,
        seconds=4.0,
        fps=24,
        length_frames=97,
    )

    service.create_and_enqueue(request, workflow_key="undress")

    assert store.prompt_meta["combo"]["category"] == "undress"
    assert store.prompt_meta["workflow"] == "undress"
