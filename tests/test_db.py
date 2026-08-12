import sqlite3
import tempfile
import unittest
from pathlib import Path

from field_transcriber.config import Config
from field_transcriber.db import connect, initialize


class DatabaseTests(unittest.TestCase):
    def test_initialize_is_idempotent_and_creates_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(root=Path(directory))
            initialize(config)
            initialize(config)
            with connect(config) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertTrue({"recordings", "jobs", "attempts"} <= tables)
                self.assertTrue({"remote_executions", "transfer_objects"} <= tables)
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(jobs)")
                }
                self.assertIn("claim_token", columns)
                self.assertIn("claim_expires_at", columns)

    def test_constraints_reject_invalid_job_state(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(root=Path(directory))
            initialize(config)
            with connect(config) as connection:
                connection.execute(
                    "INSERT INTO recordings (sha256, original_name, size_bytes, status, current_path, ingested_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("a" * 64, "x.mp3", 1, "incoming", "/tmp/x", "t", "t"),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO jobs (recording_id, status, attempt_count, created_at, updated_at) VALUES (1, 'unknown', 0, 't', 't')"
                    )


if __name__ == "__main__":
    unittest.main()
