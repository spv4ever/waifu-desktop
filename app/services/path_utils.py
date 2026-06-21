from __future__ import annotations

from pathlib import Path


def unique_suffixed_path(target: Path) -> Path:
    """Return target or the next available sibling using -1, -2, ... suffixes."""
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
