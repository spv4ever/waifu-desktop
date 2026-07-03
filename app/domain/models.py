from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class PackCreate:
    category: str
    variant: str
    requested_n: int
    notes: str = ""
    manual_feature: str = ""
    checkpoint_base: Optional[str] = None
    checkpoint_refiner: Optional[str] = None
    combination_key: Optional[str] = None
    nsfw_tag_count: Optional[int] = None


@dataclass(frozen=True)
class DollimagesPackCreate:
    typology: str
    repetitions: int
    workflow_key: str = "dollimages"
    manual_text: str = ""
    checkpoint_base: Optional[str] = None
    reference_image: Optional[str] = None
    group_name: Optional[str] = None
    faceswap_enabled: bool = True


@dataclass(frozen=True)
class DollimagesManualPromptCreate:
    typology: str
    repetitions: int
    title: str
    prompt_text: str
    workflow_key: str = "dollimages"
    checkpoint_base: Optional[str] = None
    reference_image: Optional[str] = None
    faceswap_enabled: bool = True


@dataclass(frozen=True)
class AnimeGenerationCreate:
    list_name: str
    prompt_title: str
    prompt_text: str
    characters: list[str]
    quantity_per_character: int
    fixed_outfit: Optional[str] = None
    manual_outfit_text: str = ""
    checkpoint_base: Optional[str] = None
    checkpoint_refiner: Optional[str] = None


@dataclass(frozen=True)
class ManualPromptCreate:
    category: str
    variant: str
    ratio: str
    title: str
    prompt_text: str
    quantity: int
    checkpoint_base: Optional[str] = None
    notes: str = ""


@dataclass(frozen=True)
class ImageToVideoCreate:
    source_category: str
    source_prompt_id: int
    source_url: str
    source_image: str
    title: str
    prompt_text: str
    negative_text: str
    ratio: str
    width: int
    height: int
    seconds: float
    fps: int
    length_frames: int

@dataclass(frozen=True)
class PromptDraft:
    # Lo que generamos antes de persistir
    title: str
    prompt_text: str
    negative_text: str
    meta: dict[str, Any]
    combo_key: str


@dataclass(frozen=True)
class CreatedPack:
    pack_id: int
    created_prompt_item_ids: list[int]
    created_queue_job_ids: list[int]
