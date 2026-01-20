from __future__ import annotations

from app.data.db import get_connection
from app.services.queue_worker import QueueWorker


def main():
    worker = QueueWorker()
    with get_connection() as conn:
        did = worker.process_one(conn, delay_seconds=0.1)
        print("Procesado:", did)


if __name__ == "__main__":
    main()
