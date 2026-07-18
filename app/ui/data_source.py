from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from app.data.storage import get_store


@dataclass(frozen=True)
class PromptRow:
    id: int
    title: str
    prompt_text: str
    status: str
    category: str
    variant: str
    ratio: str
    checkpoint_base: str | None
    checkpoint_refiner: str | None
    has_base: bool
    has_upscale: bool
    used_in_reel: bool
    reel_priority: bool
    reel_discarded: bool
    progress: int | None
    backend_status: str | None
    datestamp: str


def _extract_category_variant(meta_json: str | None) -> tuple[str, str]:
    if not meta_json:
        return "?", "?"
    try:
        meta = json.loads(meta_json)
        combo = meta.get("combo", {})
        return str(combo.get("category", "?")), str(combo.get("variant", "?"))
    except Exception:
        return "?", "?"


def _extract_ratio(meta_json: str | None) -> str:
    if not meta_json:
        return "?"
    try:
        meta = json.loads(meta_json)
        combo = meta.get("combo", {})
        return str(
            combo.get("ratio_tag")
            or combo.get("ratio_key")
            or combo.get("ratio")
            or meta.get("ratio")
            or "?"
        )
    except Exception:
        return "?"


def _extract_checkpoints(meta_json: str | None) -> tuple[str | None, str | None]:
    if not meta_json:
        return None, None
    try:
        meta = json.loads(meta_json)
        checkpoints = meta.get("checkpoints", {})
        if not isinstance(checkpoints, dict):
            return None, None
        base = checkpoints.get("base")
        refiner = checkpoints.get("refiner")
        return str(base) if base else None, str(refiner) if refiner else None
    except Exception:
        return None, None


def fetch_prompt_filters() -> dict[str, list[str]]:
    store = get_store()
    return store.fetch_prompt_filters()


def fetch_prompt_status_counts() -> dict[str, int]:
    store = get_store()
    counts = store.fetch_prompt_status_counts()
    eta_seconds = store.fetch_queue_eta_seconds()
    if eta_seconds is not None:
        counts["ETA_SECONDS"] = eta_seconds
    return counts


def fetch_variants_for_category(category: str | None) -> list[str]:
    store = get_store()
    return store.fetch_variants_for_category(category)


def fetch_category_production_counts() -> list[tuple[str, int]]:
    store = get_store()
    return store.fetch_category_production_counts()


def fetch_dollimages_reel_group_counts(typology: str | None = None) -> dict[str, int]:
    store = get_store()
    return store.fetch_dollimages_reel_group_counts(typology=typology)


def fetch_dollimages_reel_available_count(
    *,
    typology: str | None,
    group_name: str | None,
) -> int:
    store = get_store()
    return store.fetch_dollimages_reel_available_count(typology=typology, group_name=group_name)


def fetch_prompts(
    *,
    limit: int = 50,
    prompt_id: int | None = None,
    category: str | None = None,
    variant: str | None = None,
    status: str | None = None,
    ratio: str | None = None,
    checkpoint_base: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort_order: str = "desc",
) -> list[PromptRow]:
    dt_from = _parse_db_datetime(date_from) if date_from else None
    dt_to = _parse_db_datetime(date_to) if date_to else None

    store = get_store()
    rows = store.fetch_prompts(
        limit=limit,
        prompt_id=prompt_id,
        category=category,
        variant=variant,
        status=status,
        ratio=ratio,
        checkpoint_base=checkpoint_base,
        date_from=_format_db_datetime(dt_from) if dt_from else None,
        date_to=_format_db_datetime(dt_to) if dt_to else None,
        sort_order=sort_order,
    )

    result: list[PromptRow] = []
    for r in rows:
        row_status = str(r["status"])
        job_progress = r.get("job_progress")
        job_status = r.get("job_status")
        job_backend_status = r.get("job_backend_status")
        category_value, variant_value = _extract_category_variant(r.get("meta_json"))
        ratio_value = _extract_ratio(r.get("meta_json"))
        row_checkpoint_base, checkpoint_refiner = _extract_checkpoints(r.get("meta_json"))
        row_datestamp = str(r.get("datestamp")) if r.get("datestamp") else ""
        row_dt = _parse_db_datetime(row_datestamp) if row_datestamp else None
        progress_value = _resolve_progress(row_status, job_status, job_progress)

        result.append(
            PromptRow(
                id=int(r["id"]),
                title=str(r.get("title")),
                prompt_text=str(r.get("prompt_text")),
                status=row_status,
                category=category_value,
                variant=variant_value,
                ratio=ratio_value,
                checkpoint_base=row_checkpoint_base,
                checkpoint_refiner=checkpoint_refiner,
                has_base=bool(r.get("base_image_json")),
                has_upscale=bool(r.get("upscale_image_json")),
                used_in_reel=bool(r.get("used_in_reel")),
                reel_priority=bool(r.get("reel_priority")),
                reel_discarded=bool(r.get("reel_discarded")),
                progress=progress_value,
                backend_status=str(job_backend_status) if job_backend_status else None,
                datestamp=_format_datestamp(row_datestamp),
            )
        )
    return result


def _parse_db_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_datestamp(value: str | None) -> str:
    dt = _parse_db_datetime(value)
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_db_datetime(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _resolve_progress(status: str, job_status: str | None, job_progress: int | None) -> int | None:
    if isinstance(job_progress, int) and 0 <= job_progress <= 100:
        return job_progress
    if status == "DONE":
        return 100
    if status in {"QUEUED", "SENT"}:
        return 0
    if job_status in {"PENDING", "RUNNING"}:
        return 0
    return None
