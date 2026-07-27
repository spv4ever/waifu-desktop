from app.domain.models import ImageToVideoCreate
from app.services.image2vid_service import ImageToVideoService


class _Store:
    def __init__(self) -> None:
        self.prompt_meta = None
        self.pack_kwargs = None
        self.prompt_items = []
        self.queue_jobs = []

    def create_pack(self, **kwargs) -> int:
        self.pack_kwargs = kwargs
        return 1

    def try_register_combo(self, **kwargs) -> bool:
        return True

    def create_prompt_item(self, **kwargs) -> int:
        self.prompt_meta = kwargs["meta"]
        self.prompt_items.append(kwargs)
        return len(self.prompt_items) + 1

    def create_queue_job(self, **kwargs) -> int:
        self.queue_jobs.append(kwargs)
        return len(self.queue_jobs) + 10


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


def test_image2vid_batch_enqueues_every_prompt_in_one_pack() -> None:
    store = _Store()
    service = ImageToVideoService.__new__(ImageToVideoService)
    service.store = store
    prepared_sources = []
    service._prepare_source_image = (
        lambda source_path: prepared_sources.append(source_path) or "source.png"
    )

    base = ImageToVideoCreate(
        source_category="waifu",
        source_prompt_id=10,
        source_url="",
        source_image="source.jpg",
        title="Movimiento uno",
        prompt_text="prompt uno",
        negative_text="negative",
        ratio="1:1",
        width=720,
        height=720,
        seconds=5.0,
        fps=32,
        length_frames=80,
    )
    second = ImageToVideoCreate(
        **{**base.__dict__, "title": "Movimiento dos", "prompt_text": "prompt dos"}
    )

    result = service.create_many_and_enqueue([base, second])

    assert store.pack_kwargs["requested_n"] == 2
    assert prepared_sources == ["source.jpg"]
    assert [item["prompt_text"] for item in store.prompt_items] == ["prompt uno", "prompt dos"]
    assert len(store.queue_jobs) == 2
    assert result.created_prompt_item_ids == [2, 3]
