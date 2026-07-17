from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from app.data.storage import get_store
from app.ui.data_source import (
    PromptRow,
    fetch_category_production_counts,
    fetch_prompt_filters,
    fetch_prompt_status_counts,
    fetch_prompts,
)


@dataclass(frozen=True)
class RefreshPayload:
    rows: list[PromptRow]
    filters: dict[str, list[str]]
    status_counts: dict[str, int]
    category_counts: list[tuple[str, int]]
    is_paused: bool
    resize_columns: bool


class RefreshWorker(QThread):
    result = Signal(RefreshPayload)
    failed = Signal(str)

    def __init__(
        self,
        *,
        limit: int,
        prompt_id: int | None,
        category: str | None,
        variant: str | None,
        status: str | None,
        ratio: str | None,
        checkpoint_base: str | None,
        date_from: str | None,
        date_to: str | None,
        sort_order: str,
        resize_columns: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._limit = limit
        self._prompt_id = prompt_id
        self._category = category
        self._variant = variant
        self._status = status
        self._ratio = ratio
        self._checkpoint_base = checkpoint_base
        self._date_from = date_from
        self._date_to = date_to
        self._sort_order = sort_order
        self._resize_columns = resize_columns

    def run(self) -> None:
        try:
            rows = fetch_prompts(
                limit=self._limit,
                prompt_id=self._prompt_id,
                category=self._category,
                variant=self._variant,
                status=self._status,
                ratio=self._ratio,
                checkpoint_base=self._checkpoint_base,
                date_from=self._date_from,
                date_to=self._date_to,
                sort_order=self._sort_order,
            )
            filters = fetch_prompt_filters()
            status_counts = fetch_prompt_status_counts()
            category_counts = fetch_category_production_counts()
            paused_value = get_store().kv_get("queue_paused", "false")
            payload = RefreshPayload(
                rows=rows,
                filters=filters,
                status_counts=status_counts,
                category_counts=category_counts,
                is_paused=paused_value == "true",
                resize_columns=self._resize_columns,
            )
            self.result.emit(payload)
        except Exception as exc:
            self.failed.emit(f"No se pudo refrescar la tabla: {exc}")
