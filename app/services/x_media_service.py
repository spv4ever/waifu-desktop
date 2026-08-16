from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config.settings import settings
from app.data.db import get_connection
from app.data.social_media_repository import SocialMediaPostRow, SocialMediaRepository


class SocialMediaDownloadError(RuntimeError):
    pass


class SocialMediaService:
    YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
    INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}
    TIKTOK_HOSTS = {
        "tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    }

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or settings.social_media_dir
        self.repository = SocialMediaRepository()

    @staticmethod
    def validate_url(url: str) -> str:
        cleaned = url.strip()
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Introduce un enlace público válido de X, Instagram, TikTok o YouTube.")
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
        elif host in SocialMediaService.INSTAGRAM_HOSTS:
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) < 2 or path_parts[0] not in {"p", "reel", "reels", "tv"} or not path_parts[1]:
                raise ValueError("El enlace debe apuntar a una publicación o Reel de Instagram.")
        elif host in SocialMediaService.TIKTOK_HOSTS:
            path_parts = parsed.path.strip("/").split("/")
            is_short_link = host in {"vm.tiktok.com", "vt.tiktok.com"} and bool(path_parts[0])
            is_share_link = len(path_parts) >= 2 and path_parts[0] == "t" and bool(path_parts[1])
            is_post_link = (
                len(path_parts) >= 3
                and path_parts[0].startswith("@")
                and path_parts[1] in {"video", "photo"}
                and bool(path_parts[2])
            )
            if not (is_short_link or is_share_link or is_post_link):
                raise ValueError("El enlace debe apuntar a un vídeo o publicación de TikTok.")
        else:
            raise ValueError("Introduce un enlace público válido de X, Instagram, TikTok o YouTube.")
        return cleaned

    @staticmethod
    def platform_for_url(url: str) -> str:
        host = (urlparse(url).hostname or "").lower()
        if host in SocialMediaService.YOUTUBE_HOSTS:
            return "youtube"
        if host in SocialMediaService.INSTAGRAM_HOSTS:
            return "instagram"
        if host in SocialMediaService.TIKTOK_HOSTS:
            return "tiktok"
        return "x"

    def download(self, url: str) -> SocialMediaPostRow:
        source_url = self.validate_url(url)
        platform = self.platform_for_url(source_url)
        download_url = self._canonical_x_url(source_url) if platform == "x" else source_url
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
        info: dict = {}
        yt_dlp_error: Exception | None = None
        attempts: list[tuple[str | None, dict]] = [(None, options)]
        if platform == "x":
            attempts.extend(
                (browser, {**options, "cookiesfrombrowser": (browser,)})
                for browser in self._x_cookie_browsers()
            )
        errors: list[str] = []
        for browser, attempt_options in attempts:
            try:
                with yt_dlp.YoutubeDL(attempt_options) as downloader:
                    info = downloader.extract_info(download_url, download=True)
                yt_dlp_error = None
                break
            except Exception as exc:
                yt_dlp_error = exc
                label = f"con cookies de {browser}" if browser else "sin iniciar sesión"
                errors.append(f"{label}: {self._clean_error(exc)}")
                if platform != "x":
                    raise SocialMediaDownloadError(
                        f"No se pudo descargar el contenido público: {self._clean_error(exc)}"
                    ) from exc

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

        post_id_value = str(
            info.get("id")
            or (entries[0].get("id") if entries else None)
            or self._x_status_id(source_url)
            or "post"
        )
        post_folder = platform_dir / post_id_value
        if yt_dlp_error is not None:
            try:
                files.extend(self._download_x_gallery(download_url, post_folder))
            except SocialMediaDownloadError as gallery_error:
                yt_error = "; ".join(errors) or self._clean_error(yt_dlp_error)
                raise SocialMediaDownloadError(
                    "No se pudo descargar la publicación de X. "
                    f"yt-dlp: {yt_error}. Alternativa gallery-dl: {gallery_error}. "
                    "Si el contenido está marcado como sensible, inicia sesión en X en "
                    "Chrome, Edge o Firefox y vuelve a intentarlo."
                ) from yt_dlp_error
        if post_folder.exists():
            for path in sorted(post_folder.rglob("*")):
                if path.is_file() and path.suffix.lower() not in {".json", ".part", ".ytdl"} and path.resolve() not in files:
                    files.append(path.resolve())
                    original_urls[str(path.resolve())] = None
        if not files:
            raise SocialMediaDownloadError("El enlace no contiene imágenes o vídeos descargables.")

        assets = [
            (self._media_type(path), str(path), original_urls.get(str(path)))
            for path in files
        ]
        fallback_titles = {
            "youtube": "Vídeo de YouTube",
            "instagram": "Publicación de Instagram",
            "tiktok": "Publicación de TikTok",
            "x": "Publicación de X",
        }
        fallback_title = fallback_titles[platform]
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
    def _x_status_id(url: str) -> str | None:
        match = re.search(r"/status/(\d+)", urlparse(url).path)
        return match.group(1) if match else None

    @staticmethod
    def _canonical_x_url(url: str) -> str:
        """Remove X's UI-only /video/N suffix before handing a post to extractors."""
        parsed = urlparse(url)
        path = re.sub(r"/video/\d+/?$", "", parsed.path)
        return parsed._replace(path=path, query="", fragment="").geturl()

    @staticmethod
    def _x_cookie_browsers() -> list[str]:
        """Return configured or locally installed browsers usable by yt-dlp."""
        configured = settings.x_cookies_browser
        if configured and configured != "auto":
            return [] if configured in {"none", "off"} else [configured]

        local = Path(os.getenv("LOCALAPPDATA", ""))
        roaming = Path(os.getenv("APPDATA", ""))
        candidates = {
            "chrome": local / "Google" / "Chrome" / "User Data",
            "edge": local / "Microsoft" / "Edge" / "User Data",
            "firefox": roaming / "Mozilla" / "Firefox" / "Profiles",
        }
        return [
            browser
            for browser, path in candidates.items()
            if str(path) != "." and path.exists()
        ]

    @staticmethod
    def _clean_error(error: object) -> str:
        """Remove terminal control codes that should never be shown in a dialog."""
        ansi_escape = r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))"
        return re.sub(ansi_escape, "", str(error)).strip()

    @staticmethod
    def _download_x_gallery(url: str, post_folder: Path) -> list[Path]:
        """Use gallery-dl for photo-only X posts, which yt-dlp does not support."""
        post_folder.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "gallery_dl",
            "--destination",
            str(post_folder),
            "--no-mtime",
            url,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise SocialMediaDownloadError(str(exc)) from exc
        if result.returncode:
            detail = SocialMediaService._clean_error(result.stderr or result.stdout)
            raise SocialMediaDownloadError(detail or "gallery-dl terminó con un error desconocido.")
        files = [
            path.resolve()
            for path in sorted(post_folder.rglob("*"))
            if path.is_file() and path.suffix.lower() not in {".json", ".part"}
        ]
        if not files:
            raise SocialMediaDownloadError("gallery-dl no encontró imágenes descargables.")
        return files

    @staticmethod
    def _media_type(path: Path) -> str:
        if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
            return "video"
        return "image"


# Compatibilidad con importaciones existentes.
XMediaService = SocialMediaService
XMediaDownloadError = SocialMediaDownloadError
