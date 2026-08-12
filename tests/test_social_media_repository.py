from __future__ import annotations

import sqlite3
from pathlib import Path

from app.data.social_media_repository import SocialMediaRepository


def make_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((Path(__file__).parents[1] / "app/data/schema.sql").read_text(encoding="utf-8"))
    return conn


def test_repository_saves_post_and_all_assets() -> None:
    conn = make_connection()
    repository = SocialMediaRepository()

    post_id = repository.save_download(
        conn,
        source_url="https://x.com/user/status/42",
        external_id="42",
        title="Título del post",
        description="Descripción completa",
        author="user",
        assets=[("image", "/media/one.jpg", None), ("video", "/media/two.mp4", "https://cdn/two")],
    )

    posts = repository.list_posts(conn)
    assert posts[0].id == post_id
    assert posts[0].title == "Título del post"
    assert [asset.media_type for asset in posts[0].assets] == ["image", "video"]


def test_repository_updates_existing_source_without_duplicates() -> None:
    conn = make_connection()
    repository = SocialMediaRepository()
    values = dict(source_url="https://x.com/user/status/42", external_id="42", description="Text", author=None)
    first_id = repository.save_download(conn, title="Old", assets=[("image", "/old.jpg", None)], **values)
    second_id = repository.save_download(conn, title="New", assets=[("video", "/new.mp4", None)], **values)

    posts = repository.list_posts(conn)
    assert first_id == second_id
    assert len(posts) == 1
    assert posts[0].title == "New"
    assert posts[0].assets[0].local_path == "/new.mp4"
