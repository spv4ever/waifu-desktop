from __future__ import annotations

from app.data.db import get_connection
from app.data.kv_store import KVStore
from app.services.queue_worker import QueueWorker


def main():
    kv = KVStore()
    worker = QueueWorker()
    with get_connection() as conn:
        with conn:
            kv.set(conn, "queue_paused", "false")
            worker.recover_inflight_jobs(conn)
    print("OK: cola reanudada")


if __name__ == "__main__":
    main()
