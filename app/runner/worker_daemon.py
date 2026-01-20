from __future__ import annotations

import time

from app.data.db import get_connection
from app.services.queue_worker import QueueWorker


def main():
    worker = QueueWorker()

    print("Worker arrancado. CTRL+C para parar.")
    while True:
        with get_connection() as conn:
            result = worker.process_one(conn, delay_seconds=0.2)

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
