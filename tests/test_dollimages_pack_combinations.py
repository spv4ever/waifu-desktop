from types import SimpleNamespace

from app.domain.models import DollimagesPackCreate
from app.services import dollimages_pack_service


class FakeStore:
    def __init__(self):
        self.items = []

    def list_dollimage_prompts(self, **kwargs):
        raise AssertionError(
            "El origen combinatorio no debe consultar el catálogo fijo"
        )

    def create_pack(self, **kwargs):
        self.pack = kwargs
        return 1

    def try_register_combo(self, **kwargs):
        return True

    def create_prompt_item(self, **kwargs):
        self.items.append(kwargs)
        return len(self.items)

    def create_queue_job(self, **kwargs):
        return kwargs["prompt_item_id"] + 10


def test_dollimages_pack_builds_requested_combinations(monkeypatch):
    store = FakeStore()
    options = {
        "girl_types": ["a test woman"],
        "poses": ["test pose"],
        "outfits": ["test outfit"],
        "locations": ["test location"],
        "expressions": ["test expression"],
        "lighting": ["test lighting"],
        "shots": ["test shot"],
        "styles": ["test style"],
    }
    monkeypatch.setattr(dollimages_pack_service, "get_store", lambda: store)
    monkeypatch.setattr(
        dollimages_pack_service,
        "load_app_config",
        lambda: SimpleNamespace(
            raw={"dollimages_defaults": {"width": 832, "height": 1216}}
        ),
    )
    monkeypatch.setattr(
        dollimages_pack_service,
        "load_dollimages_prompt_options",
        lambda: (
            "[girl_type], [pose], [outfit], [location], [expression], [lighting], [shot], [style]",
            options,
        ),
    )

    service = dollimages_pack_service.DollimagesPackService()
    result = service.create_pack_and_enqueue(
        None,
        DollimagesPackCreate(
            typology="sfw",
            repetitions=2,
            workflow_key="krea2",
            prompt_source="combinations",
            combination_count=3,
        ),
    )

    assert store.pack["requested_n"] == 6
    assert len(result.created_prompt_item_ids) == 6
    assert all("[" not in item["prompt_text"] for item in store.items)
    assert all(
        item["meta"]["dollimages_prompt_source"] == "combinations"
        for item in store.items
    )
    assert (
        store.items[0]["meta"]["dollimages_prompt_selection"]["girl_type"]
        == "a test woman"
    )


def test_dollimages_pack_uses_fantasy_json_for_fantasy_combinations(monkeypatch):
    store = FakeStore()
    options = {
        key: [f"fantasy {key}"]
        for key in (
            "girl_types",
            "poses",
            "outfits",
            "locations",
            "expressions",
            "lighting",
            "shots",
            "styles",
        )
    }
    monkeypatch.setattr(dollimages_pack_service, "get_store", lambda: store)
    monkeypatch.setattr(
        dollimages_pack_service,
        "load_app_config",
        lambda: SimpleNamespace(
            raw={"dollimages_defaults": {"width": 832, "height": 1216}}
        ),
    )
    monkeypatch.setattr(
        dollimages_pack_service,
        "load_dollimages_themed_prompt_options",
        lambda prompt_source: (
            "[girl_type], [pose], [outfit], [location], [expression], [lighting], [shot], [style]",
            options,
        ),
    )

    result = dollimages_pack_service.DollimagesPackService().create_pack_and_enqueue(
        None,
        DollimagesPackCreate(
            typology="sfw",
            repetitions=1,
            workflow_key="krea2",
            prompt_source="fantasy_combinations",
            combination_count=2,
        ),
    )

    assert len(result.created_prompt_item_ids) == 2
    assert all(
        item["meta"]["dollimages_prompt_source"] == "fantasy_combinations"
        for item in store.items
    )
    assert all("fantasy girl_types" in item["prompt_text"] for item in store.items)
