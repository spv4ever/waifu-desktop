from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from app.config.settings import settings
from app.data.db import get_connection
from app.data.social_media_repository import SocialMediaPostRow, SocialMediaRepository


class XMediaDownloadError(RuntimeError):
    pass


class XMediaService:
    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or settings.social_media_dir / "x"
        self.repository = SocialMediaRepository()

    @staticmethod
    def validate_url(url: str) -> str:
        cleaned = url.strip()
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or host not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            raise ValueError("Introduce un enlace válido de x.com a una publicación pública.")
        if "/status/" not in parsed.path:
            raise ValueError("El enlace debe apuntar a una publicación de X (/status/...).")
        return cleaned

    def download(self, url: str) -> SocialMediaPostRow:
        source_url = self.validate_url(url)
        try:
            import yt_dlp
        except ImportError as exc:
            raise XMediaDownloadError("Falta yt-dlp. Instala las dependencias con pip install -r requirements.txt.") from exc

        self.output_dir.mkdir(parents=True, exist_ok=True)
        options = {
            "outtmpl": str(self.output_dir / "%(id)s" / "%(id)s_%(autonumber)03d.%(ext)s"),
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
            raise XMediaDownloadError(f"No se pudo descargar la publicación pública: {exc}") from exc

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
        post_folder = self.output_dir / post_id_value
        if post_folder.exists():
            for path in sorted(post_folder.iterdir()):
                if path.is_file() and path.suffix.lower() not in {".json", ".part", ".ytdl"} and path.resolve() not in files:
                    files.append(path.resolve())
                    original_urls[str(path.resolve())] = None
        if not files:
            raise XMediaDownloadError("La publicación no contiene imágenes o vídeos descargables.")

        assets = [
            (self._media_type(path), str(path), original_urls.get(str(path)))
            for path in files
        ]
        title = str(info.get("title") or info.get("description") or "Publicación de X").strip()
        description = str(info.get("description") or info.get("fulltitle") or title).strip()
        author = info.get("uploader") or info.get("channel") or info.get("creator")
        with get_connection() as conn:
            post_id = self.repository.save_download(
                conn, source_url=source_url, external_id=post_id_value,
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
