from __future__ import annotations

from app.services.queue_worker import QueueWorker


def main():
    worker = QueueWorker()
    did = worker.process_one(delay_seconds=0.1)
    print("Procesado:", did)


if __name__ == "__main__":
    main()
