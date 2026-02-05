from __future__ import annotations

import argparse

from app.config.dollimages_prompts import load_dollimages_prompts
from app.config.settings import settings
from app.data.storage import get_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa prompts Dollimages desde JSON.")
    parser.add_argument(
        "--path",
        default=settings.dollimages_prompts_json,
        help="Ruta al JSON de prompts (por defecto usa DOLLIMAGES_PROMPTS_JSON).",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Elimina los prompts existentes antes de importar.",
    )
    args = parser.parse_args()

    prompts = load_dollimages_prompts(args.path)
    inserted = get_store().import_dollimage_prompts(prompts, replace=args.replace)
    print(f"Importados {inserted} prompts desde {args.path}")


if __name__ == "__main__":
    main()
