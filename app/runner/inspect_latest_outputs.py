from __future__ import annotations

import json
from app.data.storage import get_store


def main():
    store = get_store()
    rows = store.fetch_prompts(limit=50, sort_order="desc")
    row = next(
        (item for item in rows if item.get("base_image_json") or item.get("upscale_image_json")),
        None,
    )

    if not row:
        print("No hay outputs guardados todavía.")
        return

    print("PromptItem ID:", row["id"])
    print("Title:", row.get("title"))

    base = json.loads(row["base_image_json"]) if row.get("base_image_json") else None
    up = json.loads(row["upscale_image_json"]) if row.get("upscale_image_json") else None

    print("\nBASE:", base)
    print("UPSCALE:", up)


if __name__ == "__main__":
    main()
