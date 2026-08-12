"""SQLite schema and transaction helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import Config


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE CHECK(length(sha256) = 64),
    original_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
    status TEXT NOT NULL CHECK(status IN ('incoming', 'processed', 'quarantined')),
    current_path TEXT NOT NULL UNIQUE,
    ingested_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    recording_id INTEGER NOT NULL UNIQUE REFERENCES recordings(id),
    status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'failed', 'complete')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
    claim_token TEXT,
    claim_expires_at TEXT,
    latest_error_step TEXT,
    latest_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK (
        (status = 'processing' AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL)
        OR (status != 'processing' AND claim_token IS NULL AND claim_expires_at IS NULL)
    )
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    number INTEGER NOT NULL,
    claim_token TEXT NOT NULL,
    worker_host TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    outcome TEXT CHECK(outcome IN ('failed', 'complete')),
    error_step TEXT,
    error_detail TEXT,
    cleanup_status TEXT CHECK(cleanup_status IN ('complete', 'failed', 'not_attempted')),
    duration_seconds REAL,
    peak_gpu_memory_mb INTEGER,
    UNIQUE(job_id, number)
);
"""


def connect(config: Config) -> sqlite3.Connection:
    connection = sqlite3.connect(config.db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize(config: Config) -> None:
    for directory in (
        config.uploading_dir,
        config.incoming_dir,
        config.processed_dir,
        config.failed_dir,
        config.transcripts_dir,
        config.state_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    with connect(config) as connection:
        connection.executescript(SCHEMA)


@contextmanager
def transaction(config: Config, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    connection = connect(config)
    try:
        connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
