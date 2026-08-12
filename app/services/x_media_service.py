from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config.settings import settings
from app.data.db import get_connection
from app.data.social_media_repository import SocialMediaPostRow, SocialMediaRepository


class SocialMediaDownloadError(RuntimeError):
    pass


class SocialMediaService:
    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or settings.social_media_dir
        self.repository = SocialMediaRepository()

    @staticmethod
    def validate_url(url: str) -> str:
        cleaned = url.strip()
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Introduce un enlace público válido de X o YouTube.")
        if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            if "/status/" not in parsed.path:
                raise ValueError("El enlace debe apuntar a una publicación de X (/status/...).")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if parsed.path != "/watch" and not parsed.path.startswith(("/shorts/", "/live/")):
                raise ValueError("El enlace debe apuntar a un vídeo o Short de YouTube.")
            if parsed.path == "/watch" and not parse_qs(parsed.query).get("v"):
                raise ValueError("El enlace de YouTube no contiene un identificador de vídeo.")
            if parsed.path.startswith(("/shorts/", "/live/")) and not parsed.path.strip("/").partition("/")[2]:
                raise ValueError("El enlace de YouTube no contiene un identificador de vídeo.")
        elif host == "youtu.be":
            if not parsed.path.strip("/"):
                raise ValueError("El enlace debe apuntar a un vídeo de YouTube.")
        else:
            raise ValueError("Introduce un enlace público válido de X o YouTube.")
        return cleaned

    @staticmethod
    def platform_for_url(url: str) -> str:
        host = (urlparse(url).hostname or "").lower()
        return "youtube" if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"} else "x"

    def download(self, url: str) -> SocialMediaPostRow:
        source_url = self.validate_url(url)
        platform = self.platform_for_url(source_url)
        try:
            import yt_dlp
        except ImportError as exc:
            raise SocialMediaDownloadError("Falta yt-dlp. Instala las dependencias con pip install -r requirements.txt.") from exc

        platform_dir = self.output_dir / platform
        platform_dir.mkdir(parents=True, exist_ok=True)
        options = {
            "outtmpl": str(platform_dir / "%(id)s" / "%(id)s_%(autonumber)03d.%(ext)s"),
            "restrictfilenames": True,
            "noplaylist": False,
            "writethumbnail": True,
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(source_url, download=True)
        except Exception as exc:
            raise SocialMediaDownloadError(f"No se pudo descargar el contenido público: {exc}") from exc

        entries = [entry for entry in (info.get("entries") or [info]) if entry]
        files: list[Path] = []
        original_urls: dict[str, str | None] = {}
        for entry in entries:
            requested = entry.get("requested_downloads") or []
            candidates = [item.get("filepath") for item in requested if item.get("filepath")]
            candidates.extend([entry.get("filepath"), entry.get("_filename")])
            for candidate in candidates:
                if candidate and Path(candidate).is_file():
                    path = Path(candidate).resolve()
                    if path not in files:
                        files.append(path)
                        original_urls[str(path)] = entry.get("webpage_url") or entry.get("url")

        post_id_value = str(info.get("id") or entries[0].get("id") or "post")
        post_folder = platform_dir / post_id_value
        if post_folder.exists():
            for path in sorted(post_folder.iterdir()):
                if path.is_file() and path.suffix.lower() not in {".json", ".part", ".ytdl"} and path.resolve() not in files:
                    files.append(path.resolve())
                    original_urls[str(path.resolve())] = None
        if not files:
            raise SocialMediaDownloadError("El enlace no contiene imágenes o vídeos descargables.")

        assets = [
            (self._media_type(path), str(path), original_urls.get(str(path)))
            for path in files
        ]
        fallback_title = "Vídeo de YouTube" if platform == "youtube" else "Publicación de X"
        title = str(info.get("title") or info.get("description") or fallback_title).strip()
        description = str(info.get("description") or info.get("fulltitle") or title).strip()
        author = info.get("uploader") or info.get("channel") or info.get("creator")
        with get_connection() as conn:
            post_id = self.repository.save_download(
                conn, platform=platform, source_url=source_url, external_id=post_id_value,
                title=title, description=description, author=str(author) if author else None,
                assets=assets,
            )
            conn.commit()
        return next(post for post in self.list_posts() if post.id == post_id)

    def list_posts(self) -> list[SocialMediaPostRow]:
        with get_connection() as conn:
            return self.repository.list_posts(conn)

    @staticmethod
    def _media_type(path: Path) -> str:
        if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
            return "video"
        return "image"


# Compatibilidad con importaciones existentes.
XMediaService = SocialMediaService
XMediaDownloadError = SocialMediaDownloadError
