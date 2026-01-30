from __future__ import annotations

import time

from app.services.queue_worker import QueueWorker


def main():
    worker = QueueWorker()

    worker.recover_inflight_jobs()

    print("Worker arrancado. CTRL+C para parar.")
    while True:
        result = worker.process_one(delay_seconds=0.2)

        if result == "PAUSED":
            print("[WORKER] Cola en pausa. Durmiendo 1s...")
            time.sleep(1.0)
        elif result == "EMPTY":
            print("[WORKER] No hay jobs PENDING. Durmiendo 1s...")
            time.sleep(1.0)
        else:
            # PROCESSED: sigue del tirón (sin sleep extra)
            pass


if __name__ == "__main__":
    main()
