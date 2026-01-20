from __future__ import annotations

from app.data.db import get_connection


def main():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) as n
            FROM queue_job
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()

        print("Estado cola (queue_job):")
        if not rows:
            print("  (vacía)")
        for r in rows:
            print(f" - {r['status']}: {r['n']}")

        rows2 = conn.execute(
            """
            SELECT status, COUNT(*) as n
            FROM prompt_item
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()

        print("\nEstado prompts (prompt_item):")
        if not rows2:
            print("  (vacío)")
        for r in rows2:
            print(f" - {r['status']}: {r['n']}")


if __name__ == "__main__":
    main()
