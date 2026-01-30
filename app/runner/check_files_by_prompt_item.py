from __future__ import annotations

import json
import sys
from pathlib import Path

from app.data.storage import get_store
from app.services.output_paths import build_output_path


def main():
    if len(sys.argv) < 2:
        print("Uso: python -m app.runner.check_files_by_prompt_item <prompt_item_id>")
        return

    pid = int(sys.argv[1])

    store = get_store()
    row = store.get_prompt_item_media(pid)

    if not row:
        print("No existe prompt_item:", pid)
        return

    print("PromptItem:", pid)
    print("Title:", row.get("title") or row.get("prompt_text") or "—")

    base = json.loads(row["base_image_json"]) if row.get("base_image_json") else None
    up = json.loads(row["upscale_image_json"]) if row.get("upscale_image_json") else None

    def show(label: str, data: dict | None):
        if not data:
            print(f"\n{label}: (no data)")
            return
        p: Path = build_output_path(data)
        print(f"\n{label}:")
        print("  subfolder:", data.get("subfolder"))
        print("  filename :", data.get("filename"))
        print("  path     :", str(p))
        print("  exists   :", p.exists())

    show("BASE", base)
    show("UPSCALE", up)


if __name__ == "__main__":
    main()
