from __future__ import annotations

from app.data.storage import get_store
from app.services.queue_worker import QueueWorker


def main():
    store = get_store()
    worker = QueueWorker()
    store.kv_set("queue_paused", "false")
    worker.recover_inflight_jobs()
    print("OK: cola reanudada")


if __name__ == "__main__":
    main()
