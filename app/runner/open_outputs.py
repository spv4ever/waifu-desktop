from __future__ import annotations

import json
import sys
from pathlib import Path

from app.data.storage import get_store
from app.services.output_paths import build_output_path
from app.services.file_open import open_file, open_folder_and_select


def main():
    if len(sys.argv) < 3:
        print("Uso:")
        print("  python -m app.runner.open_outputs <prompt_item_id> base")
        print("  python -m app.runner.open_outputs <prompt_item_id> upscale")
        print("  python -m app.runner.open_outputs <prompt_item_id> folder_base")
        print("  python -m app.runner.open_outputs <prompt_item_id> folder_upscale")
        return

    pid = int(sys.argv[1])
    mode = sys.argv[2].lower()

    store = get_store()
    row = store.get_prompt_item_media(pid)

    if not row:
        print("No existe prompt_item:", pid)
        return

    base = json.loads(row["base_image_json"]) if row.get("base_image_json") else None
    up = json.loads(row["upscale_image_json"]) if row.get("upscale_image_json") else None
    meta_json = row.get("meta_json")

    workflow_key = "waifu"
    if meta_json:
        try:
            meta = json.loads(meta_json)
        except ValueError:
            meta = {}
        workflow_key = str(meta.get("workflow") or "waifu")

    def resolve(data: dict | None) -> Path:
        if not data:
            raise RuntimeError("No hay output guardado para este modo.")
        return build_output_path(data, workflow_key=workflow_key)

    if mode == "base":
        open_file(resolve(base))
    elif mode == "upscale":
        open_file(resolve(up))
    elif mode == "folder_base":
        open_folder_and_select(resolve(base))
    elif mode == "folder_upscale":
        open_folder_and_select(resolve(up))
    else:
        print("Modo desconocido:", mode)


if __name__ == "__main__":
    main()
