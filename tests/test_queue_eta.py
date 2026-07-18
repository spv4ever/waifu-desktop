from __future__ import annotations

import sqlite3

from app.data.storage import SQLiteStore


def test_queue_eta_uses_processing_time_not_queue_wait(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE queue_job(
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            started_at TEXT,
            completed_at TEXT
        );
        INSERT INTO queue_job(id, status, created_at, updated_at, started_at, completed_at) VALUES
            (1, 'DONE', '2026-01-01 10:00:00', '2026-01-01 10:10:00', '2026-01-01 10:00:00', '2026-01-01 10:01:00'),
            (2, 'DONE', '2026-01-01 10:00:00', '2026-01-01 10:11:00', '2026-01-01 10:10:00', '2026-01-01 10:11:00'),
            (3, 'PENDING', '2026-01-01 10:12:00', '2026-01-01 10:12:00', NULL, NULL);
        """
    )

    monkeypatch.setattr("app.data.storage.get_connection", lambda: conn)

    assert SQLiteStore().fetch_queue_eta_seconds() == 60


def test_queue_eta_subtracts_elapsed_time_from_running_jobs(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE queue_job(
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            started_at TEXT,
            completed_at TEXT
        );
        INSERT INTO queue_job(id, status, created_at, updated_at, started_at, completed_at) VALUES
            (1, 'DONE', datetime('now', '-10 minutes'), datetime('now', '-9 minutes'), datetime('now', '-10 minutes'), datetime('now', '-9 minutes')),
            (2, 'DONE', datetime('now', '-8 minutes'), datetime('now', '-7 minutes'), datetime('now', '-8 minutes'), datetime('now', '-7 minutes')),
            (3, 'RUNNING', datetime('now', '-30 seconds'), datetime('now', '-30 seconds'), datetime('now', '-30 seconds'), NULL),
            (4, 'PENDING', datetime('now'), datetime('now'), NULL, NULL);
        """
    )

    monkeypatch.setattr("app.data.storage.get_connection", lambda: conn)

    assert 89 <= SQLiteStore().fetch_queue_eta_seconds() <= 90
