from __future__ import annotations

import json
from typing import Any

from app.services.output_paths import build_output_path


def resolve_video_preview_url(
    *, row: dict[str, Any], video: dict[str, Any] | None
) -> str | None:
    """Return a playable local URI, falling back to the uploaded video URL."""
    if video:
        video_path = build_output_path(video, workflow_key="image2vid")
        if video_path.exists():
            return video_path.resolve().as_uri()

    if row.get("meta_json"):
        try:
            meta = json.loads(row["meta_json"])
        except (TypeError, ValueError):
            meta = {}
        if isinstance(meta, dict):
            return str(meta.get("image2vid_cloudinary_url") or "").strip() or None
    return None
