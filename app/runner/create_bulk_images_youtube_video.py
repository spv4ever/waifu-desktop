from __future__ import annotations

import argparse

from app.services.video_montage_service import VideoMontageService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea un vídeo YouTube 16:9 con imágenes Bulk Images no usadas y un MP3 de resources/audio_relax."
    )
    parser.add_argument("--category", required=True, help="Categoría Bulk Images (bulk_metadata.category).")
    parser.add_argument("--audio", required=True, help="Nombre del MP3 dentro de resources/audio_relax o ruta absoluta.")
    parser.add_argument("--seconds-per-image", type=float, default=None, help="Segundos base por imagen antes del fundido.")
    parser.add_argument("--transition", type=float, default=None, help="Duración del fundido entre imágenes.")
    parser.add_argument("--resolution", choices=["4k", "1080p"], default="4k", help="Resolución de salida 16:9.")
    args = parser.parse_args()

    result = VideoMontageService().create_bulk_images_youtube_video(
        bulk_category=args.category,
        audio_filename=args.audio,
        image_display_seconds=args.seconds_per_image,
        transition_seconds=args.transition,
        resolution=args.resolution,
    )
    print(f"Video creado: {result.video_path}")
    print(f"Duración: {result.duration_seconds:.2f}s")
    print(f"Imágenes usadas: {len(result.source_images)}")
    print(f"Prompts marcados como usados: {', '.join(map(str, result.prompt_item_ids))}")


if __name__ == "__main__":
    main()
