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
