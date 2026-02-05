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
    checkpoint_base: Optional[str] = None
    reference_image: Optional[str] = None
    faceswap_enabled: bool = True


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
