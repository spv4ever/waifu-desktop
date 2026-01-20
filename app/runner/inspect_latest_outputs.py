from __future__ import annotations

import json
from app.data.db import get_connection


def main():
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, base_image_json, upscale_image_json
            FROM prompt_item
            WHERE base_image_json IS NOT NULL OR upscale_image_json IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if not row:
            print("No hay outputs guardados todavía.")
            return

        print("PromptItem ID:", row["id"])
        print("Title:", row["title"])

        base = json.loads(row["base_image_json"]) if row["base_image_json"] else None
        up = json.loads(row["upscale_image_json"]) if row["upscale_image_json"] else None

        print("\nBASE:", base)
        print("UPSCALE:", up)


if __name__ == "__main__":
    main()
