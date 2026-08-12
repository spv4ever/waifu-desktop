from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SocialMediaAssetRow:
    id: int
    media_type: str
    local_path: str
    original_url: str | None
    position: int


@dataclass(frozen=True)
class SocialMediaPostRow:
    id: int
    platform: str
    source_url: str
    external_id: str | None
    title: str
    description: str
    author: str | None
    created_at: str
    assets: list[SocialMediaAssetRow]


class SocialMediaRepository:
    def save_download(
        self,
        conn: sqlite3.Connection,
        *,
        platform: str = "x",
        source_url: str,
        external_id: str | None,
        title: str,
        description: str,
        author: str | None,
        assets: list[tuple[str, str, str | None]],
    ) -> int:
        conn.execute(
            """
            INSERT INTO social_media_post
                (platform, source_url, external_id, title, description, author, status)
            VALUES (?, ?, ?, ?, ?, ?, 'DOWNLOADED')
            ON CONFLICT(source_url) DO UPDATE SET
                platform = excluded.platform,
                external_id = excluded.external_id,
                title = excluded.title,
                description = excluded.description,
                author = excluded.author,
                status = 'DOWNLOADED'
            """,
            (platform, source_url, external_id, title, description, author),
        )
        post_id = int(
            conn.execute(
                "SELECT id FROM social_media_post WHERE source_url = ?", (source_url,)
            ).fetchone()[0]
        )
        conn.execute("DELETE FROM social_media_asset WHERE post_id = ?", (post_id,))
        conn.executemany(
            """
            INSERT INTO social_media_asset
                (post_id, media_type, local_path, original_url, position)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (post_id, media_type, path, original_url, position)
                for position, (media_type, path, original_url) in enumerate(assets)
            ],
        )
        return post_id

    def list_posts(self, conn: sqlite3.Connection) -> list[SocialMediaPostRow]:
        posts = conn.execute(
            """
            SELECT id, platform, source_url, external_id, title, description, author, created_at
            FROM social_media_post ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        result: list[SocialMediaPostRow] = []
        for post in posts:
            asset_rows = conn.execute(
                """
                SELECT id, media_type, local_path, original_url, position
                FROM social_media_asset WHERE post_id = ? ORDER BY position, id
                """,
                (post["id"],),
            ).fetchall()
            result.append(
                SocialMediaPostRow(
                    id=int(post["id"]), source_url=str(post["source_url"]),
                    platform=str(post["platform"]),
                    external_id=post["external_id"], title=str(post["title"]),
                    description=str(post["description"]), author=post["author"],
                    created_at=str(post["created_at"]),
                    assets=[SocialMediaAssetRow(**dict(row)) for row in asset_rows],
                )
            )
        return result
