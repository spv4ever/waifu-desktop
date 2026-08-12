from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
from typing import Any
from urllib.parse import quote

from app.data.storage import BaseStore, get_store
from app.services.output_paths import build_output_path


class XShareError(RuntimeError):
    """Raised when a four-image X post cannot be prepared."""


@dataclass(frozen=True)
class XShareDraft:
    category: str
    subcategory: str
    version: str
    images: tuple[Path, ...]
    copy: str
    compose_url: str


class XShareService:
    """Select local artwork and build an X web-composer draft.

    Browsers deliberately do not allow a URL to upload local files.  The UI
    therefore opens X with the copy filled in and places all four files on the
    desktop clipboard, ready to attach with Ctrl+V in the already-open browser.
    """

    VIRAL_HASHTAGS = ("#AnimeArt", "#Waifu", "#DigitalArt", "#AIArt")

    def __init__(self, store: BaseStore | None = None, rng: random.Random | None = None) -> None:
        self.store = store or get_store()
        self.rng = rng or random.SystemRandom()

    def options(self) -> dict[str, dict[str, list[str]]]:
        options: dict[str, dict[str, set[str]]] = {}
        for category in self.store.fetch_prompt_filters().get("categories", []):
            for row in self.store.list_prompt_images_for_category(category=category):
                subcategory = self._subcategory(row.get("meta_json"))
                version = self._version(row.get("meta_json"))
                if subcategory and version and self._image_path(row) is not None:
                    options.setdefault(category, {}).setdefault(subcategory, set()).add(version)
        return {
            category: {
                subcategory: sorted(versions, key=str.casefold)
                for subcategory, versions in sorted(
                    subcategories.items(), key=lambda item: item[0].casefold()
                )
            }
            for category, subcategories in sorted(options.items(), key=lambda item: item[0].casefold())
        }

    def create_draft(self, category: str, subcategory: str, version: str) -> XShareDraft:
        candidates: list[Path] = []
        for row in self.store.list_prompt_images_for_category(category=category):
            if self._subcategory(row.get("meta_json")) != subcategory:
                continue
            if self._version(row.get("meta_json")) != version:
                continue
            path = self._image_path(row)
            if path is not None and path not in candidates:
                candidates.append(path)
        if len(candidates) < 4:
            raise XShareError(
                f"Se necesitan al menos 4 imágenes disponibles en {category} / {subcategory} / {version}; "
                f"solo se encontraron {len(candidates)}."
            )

        images = tuple(self.rng.sample(candidates, 4))
        category_tag = self._hashtag(category)
        subcategory_tag = self._hashtag(subcategory)
        tags = list(dict.fromkeys((*self.VIRAL_HASHTAGS, category_tag, subcategory_tag)))
        copy = f"¿Cuál es tu favorita? ✨\n\n{' '.join(tags)}"
        compose_url = f"https://x.com/intent/post?text={quote(copy, safe='')}"
        return XShareDraft(category, subcategory, version, images, copy, compose_url)

    @staticmethod
    def _subcategory(meta_json: Any) -> str | None:
        try:
            meta = json.loads(meta_json) if isinstance(meta_json, str) else (meta_json or {})
        except (json.JSONDecodeError, TypeError):
            return None
        combo = meta.get("combo", {}) if isinstance(meta, dict) else {}
        value = (
            combo.get("subcategory")
            or meta.get("anime_character_list")
            or meta.get("dollimages_prompt_source")
            or meta.get("dollimages_group")
        )
        cleaned = str(value).strip() if value is not None else ""
        return cleaned or None

    @staticmethod
    def _version(meta_json: Any) -> str | None:
        try:
            meta = json.loads(meta_json) if isinstance(meta_json, str) else (meta_json or {})
        except (json.JSONDecodeError, TypeError):
            return None
        combo = meta.get("combo", {}) if isinstance(meta, dict) else {}
        value = combo.get("variant") if isinstance(combo, dict) else None
        cleaned = str(value).strip() if value is not None else ""
        return cleaned or None

    @staticmethod
    def _hashtag(value: str) -> str:
        words = re.findall(r"[^\W_]+", value, flags=re.UNICODE)
        return "#" + "".join(word[:1].upper() + word[1:] for word in words)

    @staticmethod
    def _image_path(row: dict[str, Any]) -> Path | None:
        raw = row.get("upscale_image_json") or row.get("base_image_json")
        if not raw:
            return None
        try:
            image = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(image, dict):
            return None
        meta_raw = row.get("meta_json")
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
        except (json.JSONDecodeError, TypeError):
            meta = {}
        workflow = meta.get("workflow") if isinstance(meta, dict) else None
        path = build_output_path(image, workflow_key=str(workflow) if workflow else None).resolve()
        return path if path.is_file() else None
