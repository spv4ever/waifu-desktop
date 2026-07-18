from __future__ import annotations

import sqlite3

from app.data.storage import SQLiteStore


def test_queue_eta_uses_processing_time_not_queue_wait(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE prompt_item(id INTEGER PRIMARY KEY, status TEXT NOT NULL);
        CREATE TABLE queue_job(
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            started_at TEXT,
            completed_at TEXT
        );
        INSERT INTO prompt_item(id, status) VALUES
            (1, 'DONE'),
            (2, 'DONE'),
            (3, 'QUEUED');
        INSERT INTO queue_job(id, status, created_at, updated_at, started_at, completed_at) VALUES
            (1, 'DONE', '2026-01-01 10:00:00', '2026-01-01 10:10:00', '2026-01-01 10:00:00', '2026-01-01 10:01:00'),
            (2, 'DONE', '2026-01-01 10:00:00', '2026-01-01 10:11:00', '2026-01-01 10:10:00', '2026-01-01 10:11:00');
        """
    )

    monkeypatch.setattr("app.data.storage.get_connection", lambda: conn)

    assert SQLiteStore().fetch_queue_eta_seconds() == 60
