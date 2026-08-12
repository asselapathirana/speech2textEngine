import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from field_transcriber.commands import CommandRunner, scrub
from field_transcriber.config import Config
from field_transcriber.db import connect, initialize
from field_transcriber.jobs import retry_job
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

    def test_running_command_does_not_block_on_large_stderr(self):
        running = CommandRunner().start(
            [sys.executable, "-c", "import sys; sys.stderr.write('x' * 1_000_000)"]
        )
        result = running.wait(timeout=10)
        self.assertTrue(result.ok)
        self.assertLessEqual(len(result.stderr), 2000)

    def test_unexpected_failure_records_attempt(self):
        class ExplodingRunner:
            def run(self, args, *, secrets=()):
                raise ValueError("unexpected failure")

        with patch.dict(os.environ, {"HF_TOKEN": "test-token"}):
            with self.assertRaisesRegex(DomainError, "unexpected failure"):
                run_next(self.config, runner=ExplodingRunner())
        with connect(self.config) as connection:
            job = connection.execute("SELECT status, latest_error_step FROM jobs").fetchone()
            attempt = connection.execute("SELECT outcome, error_step FROM attempts").fetchone()
        self.assertEqual(tuple(job), ("failed", "controller_unexpected"))
        self.assertEqual(tuple(attempt), ("failed", "controller_unexpected"))

    def test_cleanup_failure_is_recorded_without_reverting_completion(self):
        fixture = Path(__file__).parent / "fixtures" / "transcript_valid.json"

        class Finished:
            def poll(self):
                return 0

            def wait(self, timeout=None):
                return CommandResult(("ssh",), 0, "", "")

        class Runner:
            def run(inner_self, args, *, secrets=()):
                if args[0] == "scp" and ":" in args[1]:
                    target = Path(args[2])
                    document = __import__("json").loads(fixture.read_text())
                    with connect(self.config) as connection:
                        document["recording"]["sha256"] = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
                    target.write_text(__import__("json").dumps(document))
                if args[0] == "ssh" and "rm -rf" in args[-1]:
                    return CommandResult(tuple(args), 1, "", "cleanup failed")
                return CommandResult(tuple(args), 0, "", "")

            def start(self, args, *, secrets=()):
                return Finished()

        with patch.dict(os.environ, {"HF_TOKEN": "test-token"}):
            result = run_next(self.config, runner=Runner())
        self.assertEqual(result["cleanup"], "failed")
        with connect(self.config) as connection:
            row = connection.execute("SELECT j.status, a.cleanup_status FROM jobs j JOIN attempts a ON a.job_id=j.id").fetchone()
        self.assertEqual(tuple(row), ("complete", "failed"))

    def test_failed_upload_can_retry_to_completion(self):
        fixture = Path(__file__).parent / "fixtures" / "transcript_valid.json"

        class FailingRunner:
            def run(self, args, *, secrets=()):
                if args[0] == "scp":
                    return CommandResult(tuple(args), 1, "", "network down")
                return CommandResult(tuple(args), 0, "", "")

        with patch.dict(os.environ, {"HF_TOKEN": "test-token"}):
            with self.assertRaises(DomainError):
                run_next(self.config, runner=FailingRunner())
        with connect(self.config) as connection:
            job_id = connection.execute("SELECT id FROM jobs").fetchone()[0]
        retry_job(self.config, job_id)

        class Finished:
            def poll(self):
                return 0

            def wait(self, timeout=None):
                return CommandResult(("ssh",), 0, "", "")

        class SuccessfulRunner:
            def run(inner_self, args, *, secrets=()):
                if args[0] == "scp" and ":" in args[1]:
                    target = Path(args[2])
                    document = __import__("json").loads(fixture.read_text())
                    with connect(self.config) as connection:
                        document["recording"]["sha256"] = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
                    target.write_text(__import__("json").dumps(document))
                return CommandResult(tuple(args), 0, "", "")

            def start(self, args, *, secrets=()):
                return Finished()

        with patch.dict(os.environ, {"HF_TOKEN": "test-token"}):
            result = run_next(self.config, runner=SuccessfulRunner())
        self.assertEqual(result["result"], "complete")
        with connect(self.config) as connection:
            outcomes = [row[0] for row in connection.execute("SELECT outcome FROM attempts ORDER BY number")]
        self.assertEqual(outcomes, ["failed", "complete"])


if __name__ == "__main__":
    unittest.main()
