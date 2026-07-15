from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BULK_IMAGES_PROMPTS_PATH = Path("resources/config/bulk_images_prompts.json")


@dataclass(frozen=True)
class BulkImagePrompt:
    id: str
    title: str
    category: str
    subcategory: str
    collection: str
    subject: str
    style: str
    mood: str
    environment: str
    lighting: str
    camera: str
    composition: str
    color_palette: str
    ratio: str
    model_hint: str
    workflow_hint: str
    positive_prompt: str
    negative_prompt: str
    tags: list[str] = field(default_factory=list)
    priority: int = 100
    status: str = "draft"
    enabled: bool = True
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BulkImagePrompt":
        return cls(
            id=str(data.get("id", "")).strip(),
            title=str(data.get("title", "")).strip(),
            category=str(data.get("category", "Uncategorized")).strip() or "Uncategorized",
            subcategory=str(data.get("subcategory", "General")).strip() or "General",
            collection=str(data.get("collection", "Default")).strip() or "Default",
            subject=str(data.get("subject", "")).strip(),
            style=str(data.get("style", "")).strip(),
            mood=str(data.get("mood", "")).strip(),
            environment=str(data.get("environment", "")).strip(),
            lighting=str(data.get("lighting", "")).strip(),
            camera=str(data.get("camera", "")).strip(),
            composition=str(data.get("composition", "")).strip(),
            color_palette=str(data.get("color_palette", "")).strip(),
            ratio=str(data.get("ratio", "")).strip(),
            model_hint=str(data.get("model_hint", "")).strip(),
            workflow_hint=str(data.get("workflow_hint", "")).strip(),
            positive_prompt=str(data.get("positive_prompt", "")).strip(),
            negative_prompt=str(data.get("negative_prompt", "")).strip(),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()],
            priority=int(data.get("priority", 100)),
            status=str(data.get("status", "draft")).strip() or "draft",
            enabled=bool(data.get("enabled", True)),
            notes=str(data.get("notes", "")).strip(),
        )


def load_bulk_image_prompts(path: Path = DEFAULT_BULK_IMAGES_PROMPTS_PATH) -> list[BulkImagePrompt]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    prompts = payload.get("prompts", [])
    return sorted(
        (BulkImagePrompt.from_dict(item) for item in prompts),
        key=lambda item: (item.category.lower(), item.subcategory.lower(), item.priority, item.title.lower()),
    )
