from __future__ import annotations

from app.data.db import get_connection
from app.data.kv_store import KVStore


def main():
    kv = KVStore()
    with get_connection() as conn:
        paused = kv.get(conn, "queue_paused", "false")
    print("queue_paused =", paused)


if __name__ == "__main__":
    main()
