from __future__ import annotations

from app.services.path_utils import unique_suffixed_path


def test_unique_suffixed_path_returns_original_when_available(tmp_path):
    target = tmp_path / "reference.png"

    assert unique_suffixed_path(target) == target


def test_unique_suffixed_path_uses_hyphenated_counter(tmp_path):
    (tmp_path / "reference.png").write_bytes(b"first")
    (tmp_path / "reference-1.png").write_bytes(b"second")

    assert unique_suffixed_path(tmp_path / "reference.png") == tmp_path / "reference-2.png"
