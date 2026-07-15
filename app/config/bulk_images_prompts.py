from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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


def bulk_image_prompts_example_payload() -> dict[str, Any]:
    return {
        "library_name": "Bulk Images",
        "description": "Ejemplo para importar prompts masivos en Bulk Images.",
        "prompts": [
            {
                "id": "bulk-example-001",
                "title": "Retrato cinematográfico de ejemplo",
                "category": "Portrait",
                "subcategory": "Cinematic",
                "collection": "Import Example",
                "subject": "young woman with silver hair",
                "style": "cinematic digital art",
                "mood": "confident and serene",
                "environment": "neon city rooftop at night",
                "lighting": "soft rim light, volumetric glow",
                "camera": "85mm lens, shallow depth of field",
                "composition": "centered portrait, upper body",
                "color_palette": "teal, magenta, deep blue",
                "ratio": "2:3",
                "model_hint": "krea2",
                "workflow_hint": "bulk_images_default",
                "positive_prompt": "cinematic portrait of a young woman with silver hair on a neon city rooftop at night, soft rim light, volumetric glow, teal and magenta palette, 85mm lens, shallow depth of field, highly detailed digital art",
                "negative_prompt": "low quality, blurry, distorted hands, extra fingers, watermark, text",
                "tags": ["portrait", "cinematic", "neon"],
                "priority": 10,
                "status": "ready",
                "enabled": True,
                "notes": "Duplica este objeto para añadir más prompts. El campo id debe ser único."
            }
        ],
    }


def _read_bulk_image_prompts_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"library_name": "Bulk Images", "prompts": []}
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("El JSON debe ser un objeto con una clave 'prompts'.")
    if not isinstance(payload.get("prompts", []), list):
        raise ValueError("La clave 'prompts' debe contener una lista.")
    return payload


def import_bulk_image_prompts(import_path: Path, destination_path: Path = DEFAULT_BULK_IMAGES_PROMPTS_PATH) -> tuple[int, int]:
    with import_path.open("r", encoding="utf-8") as fh:
        imported_payload = json.load(fh)
    if not isinstance(imported_payload, dict) or not isinstance(imported_payload.get("prompts"), list):
        raise ValueError("El archivo debe tener el formato {'prompts': [...]}.")

    imported_prompts = [BulkImagePrompt.from_dict(item) for item in imported_payload["prompts"] if isinstance(item, dict)]
    if not imported_prompts:
        raise ValueError("El archivo no contiene prompts válidos para importar.")

    for prompt in imported_prompts:
        if not prompt.id:
            raise ValueError("Todos los prompts importados deben tener un 'id'.")
        if not prompt.title:
            raise ValueError(f"El prompt '{prompt.id}' debe tener un 'title'.")
        if not prompt.positive_prompt:
            raise ValueError(f"El prompt '{prompt.id}' debe tener un 'positive_prompt'.")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_payload = _read_bulk_image_prompts_payload(destination_path)
    existing_prompts = destination_payload.get("prompts", [])
    existing_by_id = {str(item.get("id", "")).strip(): item for item in existing_prompts if isinstance(item, dict)}

    added = 0
    updated = 0
    for prompt in imported_prompts:
        item = asdict(prompt)
        if prompt.id in existing_by_id:
            updated += 1
        else:
            added += 1
        existing_by_id[prompt.id] = item

    destination_payload["prompts"] = list(existing_by_id.values())
    with destination_path.open("w", encoding="utf-8") as fh:
        json.dump(destination_payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return added, updated


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
