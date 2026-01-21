from __future__ import annotations

import time
from PySide6.QtCore import QThread, Signal

from app.data.db import get_connection
from app.services.queue_worker import QueueWorker


class WorkerThread(QThread):
    status = Signal(str)         # mensajes cortos (RUNNING / IDLE / PAUSED)
    processed = Signal()         # para refrescar UI
    log = Signal(str)            # logs del worker

    def __init__(self, poll_idle_seconds: float = 1.0, delay_seconds: float = 0.0) -> None:
        super().__init__()
        self._stop = False
        self.poll_idle_seconds = poll_idle_seconds
        self.delay_seconds = delay_seconds
        self.worker = QueueWorker(log_callback=self._emit_log)

    def _emit_log(self, message: str) -> None:
        self.log.emit(message)

    def stop(self) -> None:
        self._stop = True

    def set_delay_seconds(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds

    def run(self) -> None:
        self.status.emit("RUNNING")
        while not self._stop:
            with get_connection() as conn:
                result = self.worker.process_one(conn, delay_seconds=self.delay_seconds)

            if result == "PAUSED":
                self.status.emit("PAUSED")
                time.sleep(self.poll_idle_seconds)
            elif result == "EMPTY":
                self.status.emit("IDLE")
                time.sleep(self.poll_idle_seconds)
            else:
                # PROCESSED
                self.status.emit("RUNNING")
                self.processed.emit()

        self.status.emit("STOPPED")
