from types import SimpleNamespace

from app.config.bulk_images_prompts import BulkImagePrompt
from app.services.bulk_images_service import BulkImagesEnqueueRequest, BulkImagesService


class FakeStore:
    def __init__(self):
        self.packs = []
        self.combos = []
        self.prompt_items = []
        self.queue_jobs = []

    def create_pack(self, **kwargs):
        self.packs.append(kwargs)
        return 10

    def try_register_combo(self, **kwargs):
        self.combos.append(kwargs)
        return True

    def create_prompt_item(self, **kwargs):
        self.prompt_items.append(kwargs)
        return len(self.prompt_items)

    def create_queue_job(self, **kwargs):
        self.queue_jobs.append(kwargs)
        return len(self.queue_jobs) + 100


def _prompt(**overrides):
    values = dict(
        id="bulk-1",
        title="Bulk prompt",
        category="portrait",
        subcategory="studio",
        collection="default",
        subject="model",
        style="cinematic",
        mood="calm",
        environment="studio",
        lighting="softbox",
        camera="85mm",
        composition="close-up",
        color_palette="warm",
        ratio="3:4",
        model_hint="dreamshaper",
        workflow_hint="bulk_images_default",
        positive_prompt="portrait prompt",
        negative_prompt="negative prompt",
        tags=["tag-a"],
        quantity=1,
        priority=25,
        status="ready",
        enabled=True,
        notes="",
    )
    values.update(overrides)
    return BulkImagePrompt(**values)


def test_create_prompts_and_enqueue_preserves_bulk_prompt_text_and_metadata(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("app.services.bulk_images_service.get_store", lambda: store)
    monkeypatch.setattr(
        "app.services.bulk_images_service.load_app_config",
        lambda: SimpleNamespace(defaults={"width": 1024, "height": 1024}, ratios={"3:4": (768, 1024)}),
    )

    service = BulkImagesService()
    result = service.create_prompts_and_enqueue(BulkImagesEnqueueRequest(prompts=[_prompt()]))

    assert result.pack_id == 10
    assert store.packs == [
        {
            "category": "bulk_images",
            "variant": "library",
            "requested_n": 1,
            "notes": "bulk_images_prompt_library",
        }
    ]
    assert store.prompt_items[0]["title"] == "Bulk prompt"
    assert store.prompt_items[0]["prompt_text"] == "portrait prompt"
    assert store.prompt_items[0]["negative_text"] == "negative prompt"
    assert store.prompt_items[0]["meta"]["bulk_prompt_id"] == "bulk-1"
    assert store.prompt_items[0]["meta"]["workflow"] == "krea2"
    assert store.prompt_items[0]["meta"]["bulk_metadata"]["workflow_hint"] == "bulk_images_default"
    assert store.prompt_items[0]["meta"].get("checkpoints") is None
    assert store.prompt_items[0]["meta"]["bulk_generation_index"] == 1
    assert store.prompt_items[0]["meta"]["bulk_generation_total"] == 1
    assert store.queue_jobs == [{"prompt_item_id": 1, "priority": 25}]


def test_create_prompts_and_enqueue_skips_disabled_prompts(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("app.services.bulk_images_service.get_store", lambda: store)
    monkeypatch.setattr(
        "app.services.bulk_images_service.load_app_config",
        lambda: SimpleNamespace(defaults={"width": 1024, "height": 1024}, ratios={}),
    )

    service = BulkImagesService()
    service.create_prompts_and_enqueue(
        BulkImagesEnqueueRequest(prompts=[_prompt(enabled=False), _prompt(id="bulk-2", title="Enabled")])
    )

    assert store.packs[0]["requested_n"] == 1
    assert len(store.prompt_items) == 1
    assert store.prompt_items[0]["title"] == "Enabled"


def test_create_prompts_and_enqueue_uses_explicit_checkpoint_override_for_dollimages(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("app.services.bulk_images_service.get_store", lambda: store)
    monkeypatch.setattr(
        "app.services.bulk_images_service.load_app_config",
        lambda: SimpleNamespace(defaults={"width": 1024, "height": 1024}, ratios={}),
    )

    service = BulkImagesService()
    service.create_prompts_and_enqueue(
        BulkImagesEnqueueRequest(
            prompts=[_prompt(model_hint="image", workflow_hint="dollimages")],
            checkpoint_base="agilPhoto_v10.safetensors",
        )
    )

    assert store.prompt_items[0]["meta"]["checkpoints"] == {
        "base": "agilPhoto_v10.safetensors",
        "refiner": "agilPhoto_v10.safetensors",
    }


def test_create_prompts_and_enqueue_falls_back_to_krea2_for_unknown_workflow_hint(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("app.services.bulk_images_service.get_store", lambda: store)
    monkeypatch.setattr(
        "app.services.bulk_images_service.load_app_config",
        lambda: SimpleNamespace(defaults={"width": 1024, "height": 1024}, ratios={}),
    )

    service = BulkImagesService()
    service.create_prompts_and_enqueue(BulkImagesEnqueueRequest(prompts=[_prompt(workflow_hint="legacy_default")]))

    assert store.prompt_items[0]["meta"]["workflow"] == "krea2"


def test_create_prompts_and_enqueue_creates_requested_quantity_per_prompt(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("app.services.bulk_images_service.get_store", lambda: store)
    monkeypatch.setattr(
        "app.services.bulk_images_service.load_app_config",
        lambda: SimpleNamespace(defaults={"width": 1024, "height": 1024}, ratios={}),
    )

    service = BulkImagesService()
    result = service.create_prompts_and_enqueue(BulkImagesEnqueueRequest(prompts=[_prompt(quantity=3)]))

    assert store.packs[0]["requested_n"] == 3
    assert result.created_prompt_item_ids == [1, 2, 3]
    assert [item["meta"]["bulk_generation_index"] for item in store.prompt_items] == [1, 2, 3]
    assert [item["meta"]["bulk_generation_total"] for item in store.prompt_items] == [3, 3, 3]
    assert len(store.queue_jobs) == 3


def test_create_prompts_and_enqueue_uses_quantity_per_prompt_override(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr("app.services.bulk_images_service.get_store", lambda: store)
    monkeypatch.setattr(
        "app.services.bulk_images_service.load_app_config",
        lambda: SimpleNamespace(defaults={"width": 1024, "height": 1024}, ratios={}),
    )

    service = BulkImagesService()
    result = service.create_prompts_and_enqueue(
        BulkImagesEnqueueRequest(prompts=[_prompt(quantity=5)], quantity_per_prompt=2)
    )

    assert store.packs[0]["requested_n"] == 2
    assert result.created_prompt_item_ids == [1, 2]
    assert [item["meta"]["bulk_generation_index"] for item in store.prompt_items] == [1, 2]
    assert [item["meta"]["bulk_generation_total"] for item in store.prompt_items] == [2, 2]
    assert [item["meta"]["bulk_metadata"]["quantity"] for item in store.prompt_items] == [2, 2]
    assert [item["meta"]["bulk_metadata"]["library_quantity"] for item in store.prompt_items] == [5, 5]
    assert len(store.queue_jobs) == 2
