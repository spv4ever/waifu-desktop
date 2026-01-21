from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class PackCreate:
    category: str
    variant: str
    requested_n: int
    notes: str = ""
    checkpoint_base: Optional[str] = None
    checkpoint_refiner: Optional[str] = None


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
