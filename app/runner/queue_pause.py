from __future__ import annotations

from app.data.db import get_connection
from app.data.kv_store import KVStore


def main():
    kv = KVStore()
    with get_connection() as conn:
        with conn:
            kv.set(conn, "queue_paused", "true")
    print("OK: cola pausada")


if __name__ == "__main__":
    main()
