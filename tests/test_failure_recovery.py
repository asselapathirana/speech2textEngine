import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from field_transcriber.commands import CommandRunner, scrub
from field_transcriber.config import Config
from field_transcriber.db import connect, initialize
from field_transcriber.models import CommandResult, DomainError
from field_transcriber.orchestrator import run_next
from field_transcriber.recordings import discover


class FailureRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(root=Path(self.temp.name), worker_host="worker")
        initialize(self.config)
        (self.config.incoming_dir / "sample.mp3").write_bytes(b"audio")
        discover(self.config)

    def test_upload_failure_records_bounded_secret_safe_error(self):
        secret = "hf_secret_value"

        class FailingRunner:
            def run(self, args, *, secrets=()):
                if args[0] == "scp":
                    return CommandResult(tuple(args), 1, "", ("x" * 3000) + secret)
                return CommandResult(tuple(args), 0, "", "")

            def start(self, args, *, secrets=()):
                raise AssertionError("worker should not start")

        with patch.dict(os.environ, {"HF_TOKEN": secret}):
            with self.assertRaises(DomainError):
                run_next(self.config, runner=FailingRunner())
        with connect(self.config) as connection:
            row = connection.execute("SELECT status, latest_error_step, latest_error FROM jobs").fetchone()
        self.assertEqual(row[0], "failed")
        self.assertEqual(row[1], "worker_upload")
        self.assertLessEqual(len(row[2]), 2000)
        self.assertNotIn(secret, row[2])

    def test_scrub_bounds_and_redacts(self):
        result = scrub("a" * 3000 + "token", ("token",))
        self.assertLessEqual(len(result), 2000)
        self.assertNotIn("token", result)


if __name__ == "__main__":
    unittest.main()
