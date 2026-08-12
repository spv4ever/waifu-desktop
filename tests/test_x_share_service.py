from __future__ import annotations

import json
from pathlib import Path
import random

import pytest

from app.services.x_share_service import XShareError, XShareService


class FakeStore:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def fetch_prompt_filters(self) -> dict[str, list[str]]:
        return {"categories": ["fantasía épica"]}

    def list_prompt_images_for_category(self, *, category: str) -> list[dict[str, str]]:
        return self.rows if category == "fantasía épica" else []


def image_row(
    path: Path, subcategory: str = "elfa nocturna", version: str = "normal"
) -> dict[str, str]:
    return {
        "base_image_json": json.dumps({"filename": str(path)}),
        "upscale_image_json": "",
        "meta_json": json.dumps(
            {"combo": {"subcategory": subcategory, "variant": version}}
        ),
    }


def test_create_draft_selects_four_existing_images_and_builds_tags(tmp_path: Path) -> None:
    paths = [tmp_path / f"image-{index}.png" for index in range(6)]
    for path in paths:
        path.write_bytes(b"image")

    service = XShareService(FakeStore([image_row(path) for path in paths]), random.Random(7))
    draft = service.create_draft("fantasía épica", "elfa nocturna", "normal")

    assert len(draft.images) == 4
    assert len(set(draft.images)) == 4
    assert "#FantasíaÉpica" in draft.copy
    assert "#ElfaNocturna" in draft.copy
    assert draft.compose_url.startswith("https://x.com/intent/post?text=")


def test_options_only_includes_subcategories_with_existing_images(tmp_path: Path) -> None:
    existing = tmp_path / "existing.png"
    existing.write_bytes(b"image")
    missing = tmp_path / "missing.png"
    service = XShareService(FakeStore([image_row(existing), image_row(missing, "ausente")]))

    assert service.options() == {"fantasía épica": {"elfa nocturna": ["normal"]}}


def test_create_draft_requires_four_images(tmp_path: Path) -> None:
    paths = [tmp_path / f"image-{index}.png" for index in range(3)]
    for path in paths:
        path.write_bytes(b"image")
    service = XShareService(FakeStore([image_row(path) for path in paths]))

    with pytest.raises(XShareError, match="al menos 4"):
        service.create_draft("fantasía épica", "elfa nocturna", "normal")


def test_create_draft_does_not_mix_versions(tmp_path: Path) -> None:
    normal_paths = [tmp_path / f"normal-{index}.png" for index in range(4)]
    other_paths = [tmp_path / f"{version}.png" for version in ("sfw", "nsfw")]
    for path in [*normal_paths, *other_paths]:
        path.write_bytes(b"image")
    rows = [image_row(path) for path in normal_paths]
    rows.extend(image_row(path, version=path.stem) for path in other_paths)
    service = XShareService(FakeStore(rows), random.Random(7))

    assert service.options() == {
        "fantasía épica": {"elfa nocturna": ["normal", "nsfw", "sfw"]}
    }
    draft = service.create_draft("fantasía épica", "elfa nocturna", "normal")

    assert draft.version == "normal"
    assert set(draft.images) == set(normal_paths)
