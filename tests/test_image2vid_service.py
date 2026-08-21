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

    def update_prompt_item_meta(self, *, prompt_id, updates) -> None:
        self.prompt_items[prompt_id - 2]["meta"].update(updates)


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


def test_image2vid_long_links_segments_and_marks_only_last_as_final() -> None:
    store = _Store()
    service = ImageToVideoService.__new__(ImageToVideoService)
    service.store = store
    service._prepare_source_image = lambda _source_path: "source.png"
    request = ImageToVideoCreate(
        source_category="waifu", source_prompt_id=10, source_url="",
        source_image="source.jpg", title="Long", prompt_text="move",
        negative_text="negative", ratio="1:1", width=720, height=720,
        seconds=5.0, fps=32, length_frames=80,
    )

    result = service.create_long_and_enqueue([request, request], seed=123456)

    first_meta, second_meta = [item["meta"] for item in store.prompt_items]
    assert store.pack_kwargs["category"] == "image2vid_long"
    assert first_meta["image2vid_long_previous_prompt_id"] is None
    assert first_meta["image2vid_long_initial_source_image"] == "source.png"
    assert second_meta["image2vid_long_previous_prompt_id"] == result.created_prompt_item_ids[0]
    assert first_meta["image2vid_long_final"] is False
    assert second_meta["image2vid_long_final"] is True
    assert second_meta["image2vid_long_prompt_ids"] == result.created_prompt_item_ids
    assert first_meta["seed"] == second_meta["seed"] == 123456
    assert first_meta["image2vid_long_seed"] == second_meta["image2vid_long_seed"] == 123456


def test_image2vid_long_can_use_a_random_seed_for_each_segment(monkeypatch) -> None:
    store = _Store()
    service = ImageToVideoService.__new__(ImageToVideoService)
    service.store = store
    service._prepare_source_image = lambda _source_path: "source.png"
    request = ImageToVideoCreate(
        source_category="waifu", source_prompt_id=10, source_url="",
        source_image="source.jpg", title="Long", prompt_text="move",
        negative_text="negative", ratio="1:1", width=720, height=720,
        seconds=5.0, fps=32, length_frames=80,
    )
    seeds = iter((111, 222))
    monkeypatch.setattr(
        "app.services.image2vid_service.random.Random.randint",
        lambda *_args: next(seeds),
    )

    service.create_long_and_enqueue([request, request], fixed_seed=False)

    first_meta, second_meta = [item["meta"] for item in store.prompt_items]
    assert first_meta["seed"] == 111
    assert second_meta["seed"] == 222
    assert first_meta["image2vid_long_fixed_seed"] is False
    assert "image2vid_long_seed" not in first_meta


def test_undress_batch_reuses_source_image_for_repeated_clips() -> None:
    store = _Store()
    service = ImageToVideoService.__new__(ImageToVideoService)
    service.store = store
    prepared_sources = []
    service._prepare_source_image = (
        lambda source_path: prepared_sources.append(source_path) or "source.png"
    )
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

    result = service.create_many_and_enqueue(
        [request, request, request], workflow_key="undress"
    )

    assert store.pack_kwargs["requested_n"] == 3
    assert prepared_sources == ["source.jpg"]
    assert len(store.prompt_items) == 3
    assert len(store.queue_jobs) == 3
    assert len(result.created_prompt_item_ids) == 3
