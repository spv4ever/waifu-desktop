from app.domain.models import AnimeGenerationCreate
from app.services import anime_generation_service
from app.services.anime_generation_service import AnimeGenerationService


class FakeAnimeStore:
    def __init__(self):
        self.prompt_items = []
        self.meta_updates = []

    def save_anime_prompt(self, **kwargs):
        self.saved_prompt = kwargs
        return 11

    def save_anime_character(self, **kwargs):
        return len(getattr(self, "characters", [])) + 21

    def create_pack(self, **kwargs):
        self.pack = kwargs
        return 31

    def try_register_combo(self, **kwargs):
        return True

    def create_prompt_item(self, **kwargs):
        self.prompt_items.append(kwargs)
        return len(self.prompt_items) + 40

    def create_queue_job(self, **kwargs):
        return kwargs["prompt_item_id"] + 100


def test_anime_v5_replaces_anime_marker_and_dragon_ball_with_list_name(monkeypatch):
    store = FakeAnimeStore()
    monkeypatch.setattr(anime_generation_service, "get_store", lambda: store)

    service = AnimeGenerationService()
    result = service.create_images_and_enqueue(
        AnimeGenerationCreate(
            list_name="Personajes Naruto",
            prompt_title="Prompt",
            prompt_text="[personaje] from [anime], Dragon Ball lighting",
            characters=["Hinata"],
            quantity_per_character=1,
        )
    )

    assert result.created_prompt_item_ids == [41]
    assert store.prompt_items[0]["prompt_text"] == "Hinata from Personajes Naruto, Personajes Naruto lighting"
    assert store.prompt_items[0]["meta"]["anime_prompt_template"] == "[personaje] from [anime], Dragon Ball lighting"


def test_anime_v5_generator_combines_configurable_options(monkeypatch):
    store = FakeAnimeStore()
    monkeypatch.setattr(anime_generation_service, "get_store", lambda: store)
    monkeypatch.setattr(
        anime_generation_service,
        "load_anime_v5_prompt_options",
        lambda: {
            "locations": ["on a test rooftop"],
            "poses": ["standing in a test pose"],
            "outfits": ["a test outfit"],
            "expressions": ["a test smile"],
            "lighting": ["test cinematic lighting"],
            "shots": ["test full body shot"],
        },
    )

    service = AnimeGenerationService()
    service.create_images_and_enqueue(
        AnimeGenerationCreate(
            list_name="Sailor Moon",
            prompt_title="Generated",
            prompt_text=(
                "Adult [personaje] from [anime], single female character, [shot], [pose], "
                "[location], wearing [outfit], [expression], [lighting], SFW."
            ),
            characters=["Usagi"],
            quantity_per_character=1,
        )
    )

    prompt = store.prompt_items[0]["prompt_text"]
    assert prompt == (
        "Adult Usagi from Sailor Moon, single female character, test full body shot, "
        "standing in a test pose, on a test rooftop, wearing a test outfit, a test smile, "
        "test cinematic lighting, SFW."
    )
    assert store.saved_prompt["prompt_text"].startswith("Adult [personaje] from [anime]")
    assert store.prompt_items[0]["meta"]["anime_v5_prompt_selection"] == {
        "location": "on a test rooftop",
        "pose": "standing in a test pose",
        "outfit": "a test outfit",
        "expression": "a test smile",
        "lighting": "test cinematic lighting",
        "shot": "test full body shot",
    }
