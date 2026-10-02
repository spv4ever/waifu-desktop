from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.data.product_3d_repository import Product3DRepository


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    schema = Path(__file__).parents[1] / "app/data/schema.sql"
    connection.executescript(schema.read_text(encoding="utf-8"))
    return connection


def test_crud_and_filters(conn: sqlite3.Connection) -> None:
    repository = Product3DRepository()
    first_id = repository.create(
        conn, category="Llaveros", description="Dragón rojo",
        cost_cents=125, pvp_cents=500, stock=3,
    )
    repository.create(
        conn, category="Figuras", description="Gato articulado",
        cost_cents=250, pvp_cents=900, stock=0,
    )

    assert first_id == 1
    assert [item.description for item in repository.list(conn, category="llave")] == ["Dragón rojo"]
    assert [item.id for item in repository.list(conn, description="DRAGÓN")] == [first_id]
    assert [item.id for item in repository.list(conn, in_stock_only=True)] == [first_id]

    repository.update(
        conn, first_id, category="Llaveros", description="Dragón azul",
        cost_cents=150, pvp_cents=550, stock=8,
    )
    assert repository.list(conn, description="azul")[0].stock == 8
    repository.delete(conn, first_id)
    assert repository.list(conn, description="azul") == []


def test_rejects_invalid_product(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        Product3DRepository().create(
            conn, category="", description="Producto", cost_cents=0, pvp_cents=0, stock=0,
        )
