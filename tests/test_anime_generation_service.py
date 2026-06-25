from app.domain.models import AnimeGenerationCreate
from app.services import anime_generation_service
from app.services.anime_generation_service import AnimeGenerationService
from app.services.anime_v5_prompt_generator import AnimeV5PromptSelection


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


def test_anime_v5_generator_can_fix_outfit_and_randomize_other_options(monkeypatch):
    store = FakeAnimeStore()
    monkeypatch.setattr(anime_generation_service, "get_store", lambda: store)
    monkeypatch.setattr(
        anime_generation_service,
        "load_anime_v5_prompt_options",
        lambda: {
            "locations": ["rooftop"],
            "poses": ["standing"],
            "outfits": ["dress"],
            "expressions": ["smile"],
            "lighting": ["sunset"],
            "shots": ["full body"],
        },
    )

    service = AnimeGenerationService()
    service.create_images_and_enqueue(
        AnimeGenerationCreate(
            list_name="One Piece",
            prompt_title="Generated",
            prompt_text="[personaje] from [anime], [shot], [pose], [location], [outfit], [expression], [lighting]",
            characters=["Nami"],
            quantity_per_character=1,
            fixed_outfit="custom battle outfit",
        )
    )

    assert store.prompt_items[0]["prompt_text"] == (
        "Nami from One Piece, full body, standing, rooftop, custom battle outfit, smile, sunset"
    )
    assert store.prompt_items[0]["meta"]["anime_v5_prompt_selection"] == {
        "location": "rooftop",
        "pose": "standing",
        "outfit": "custom battle outfit",
        "expression": "smile",
        "lighting": "sunset",
        "shot": "full body",
    }


def test_anime_v5_generator_reuses_selected_options_for_all_characters(monkeypatch):
    store = FakeAnimeStore()
    selections = []
    monkeypatch.setattr(anime_generation_service, "get_store", lambda: store)
    monkeypatch.setattr(
        anime_generation_service,
        "load_anime_v5_prompt_options",
        lambda: {
            "locations": ["rooftop", "beach"],
            "poses": ["standing", "sitting"],
            "outfits": ["dress", "jacket"],
            "expressions": ["smile", "serious"],
            "lighting": ["sunset", "neon"],
            "shots": ["full body", "portrait"],
        },
    )

    def choose_once(rng, options, *, fixed_outfit=None):
        selections.append(options)
        return AnimeV5PromptSelection(
            location="rooftop",
            pose="standing",
            outfit="dress",
            expression="smile",
            lighting="sunset",
            shot="full body",
        )

    monkeypatch.setattr(anime_generation_service, "choose_anime_v5_prompt_selection", choose_once)

    service = AnimeGenerationService()
    service.create_images_and_enqueue(
        AnimeGenerationCreate(
            list_name="One Piece",
            prompt_title="Generated",
            prompt_text="[personaje] from [anime], [shot], [pose], [location], [outfit], [expression], [lighting]",
            characters=["Nami", "Robin"],
            quantity_per_character=2,
        )
    )

    assert len(selections) == 1
    assert [item["prompt_text"] for item in store.prompt_items] == [
        "Nami from One Piece, full body, standing, rooftop, dress, smile, sunset",
        "Nami from One Piece, full body, standing, rooftop, dress, smile, sunset",
        "Robin from One Piece, full body, standing, rooftop, dress, smile, sunset",
        "Robin from One Piece, full body, standing, rooftop, dress, smile, sunset",
    ]
    assert all(
        item["meta"]["anime_v5_prompt_selection"] == {
            "location": "rooftop",
            "pose": "standing",
            "outfit": "dress",
            "expression": "smile",
            "lighting": "sunset",
            "shot": "full body",
        }
        for item in store.prompt_items
    )


def test_anime_v5_injects_character_description_from_json(monkeypatch):
    store = FakeAnimeStore()
    monkeypatch.setattr(anime_generation_service, "get_store", lambda: store)

    service = AnimeGenerationService()
    service.create_images_and_enqueue(
        AnimeGenerationCreate(
            list_name="One Piece",
            prompt_title="Prompt",
            prompt_text="Adult [personaje] from [anime], [description], cinematic portrait",
            characters=[
                '{"name": "Nami", "anime": "One Piece", "description": "beautiful anime woman with long bright orange hair, large brown eyes, slim curvy figure, recognizable anime-inspired appearance"}'
            ],
            quantity_per_character=1,
        )
    )

    assert store.prompt_items[0]["prompt_text"] == (
        "Adult Nami from One Piece, beautiful anime woman with long bright orange hair, "
        "large brown eyes, slim curvy figure, recognizable anime-inspired appearance, cinematic portrait"
    )
    assert store.prompt_items[0]["meta"]["anime_character"] == "Nami"
    assert store.prompt_items[0]["meta"]["anime_character_description"].startswith("beautiful anime woman")
