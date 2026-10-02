from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Product3D:
    id: int
    category: str
    description: str
    cost_cents: int
    pvp_cents: int
    stock: int


class Product3DRepository:
    """Persistence operations for the 3D-product inventory."""

    def list(
        self,
        conn: sqlite3.Connection,
        *,
        category: str = "",
        description: str = "",
        in_stock_only: bool = False,
    ) -> list[Product3D]:
        rows = conn.execute(
            """
            SELECT id, category, description, cost_cents, pvp_cents, stock
            FROM product_3d
            WHERE (? = 0 OR stock > 0)
            ORDER BY category COLLATE NOCASE, description COLLATE NOCASE, id
            """,
            (int(in_stock_only),),
        ).fetchall()
        category_query = category.strip().casefold()
        description_query = description.strip().casefold()
        return [
            Product3D(**dict(row))
            for row in rows
            if category_query in str(row["category"]).casefold()
            and description_query in str(row["description"]).casefold()
        ]

    def create(
        self, conn: sqlite3.Connection, *, category: str, description: str,
        cost_cents: int, pvp_cents: int, stock: int,
    ) -> int:
        self._validate(category, description, cost_cents, pvp_cents, stock)
        cursor = conn.execute(
            "INSERT INTO product_3d(category, description, cost_cents, pvp_cents, stock) "
            "VALUES (?, ?, ?, ?, ?)",
            (category.strip(), description.strip(), cost_cents, pvp_cents, stock),
        )
        return int(cursor.lastrowid)

    def update(
        self, conn: sqlite3.Connection, product_id: int, *, category: str,
        description: str, cost_cents: int, pvp_cents: int, stock: int,
    ) -> None:
        self._validate(category, description, cost_cents, pvp_cents, stock)
        cursor = conn.execute(
            """UPDATE product_3d SET category=?, description=?, cost_cents=?,
               pvp_cents=?, stock=? WHERE id=?""",
            (category.strip(), description.strip(), cost_cents, pvp_cents, stock, product_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"No existe el producto {product_id}.")

    def delete(self, conn: sqlite3.Connection, product_id: int) -> None:
        conn.execute("DELETE FROM product_3d WHERE id = ?", (product_id,))

    @staticmethod
    def _validate(category: str, description: str, cost_cents: int, pvp_cents: int, stock: int) -> None:
        if not category.strip() or not description.strip():
            raise ValueError("La categoría y la descripción son obligatorias.")
        if min(cost_cents, pvp_cents, stock) < 0:
            raise ValueError("El coste, el PVP y el stock no pueden ser negativos.")
