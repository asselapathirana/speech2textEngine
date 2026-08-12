import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from field_transcriber.config import Config
from field_transcriber.db import connect, initialize
from field_transcriber.jobs import claim_next, complete_claim, processed_path, reclaim_remote_claim, reconcile_interrupted_completions, renew_claim
from field_transcriber.models import CommandResult, DomainError
from field_transcriber.orchestrator import run_next
from field_transcriber.recordings import discover


class JobClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(root=Path(self.temp.name), worker_host="worker")
        initialize(self.config)
        source = self.config.incoming_dir / "sample.mp3"
        source.write_bytes(b"audio")
        discover(self.config)

    def test_claim_is_exclusive_and_renewal_is_token_guarded(self):
        claim = claim_next(self.config)
        self.assertIsNotNone(claim)
        self.assertIsNone(claim_next(self.config))
        self.assertTrue(renew_claim(self.config, claim.job.id, claim.token))
        self.assertFalse(renew_claim(self.config, claim.job.id, "wrong"))

    def test_remote_reclaim_replaces_token_on_same_attempt(self):
        claim = claim_next(self.config)
        replacement = reclaim_remote_claim(self.config, claim.job.id, claim.attempt_id)
        self.assertEqual(replacement.attempt_id, claim.attempt_id)
        self.assertNotEqual(replacement.token, claim.token)
        with connect(self.config) as connection:
            count = connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        self.assertEqual(count, 1)

    def test_completion_requires_owned_claim_and_moves_source(self):
        claim = claim_next(self.config)
        transcript_dir = self.config.transcripts_dir / claim.recording.sha256
        transcript_dir.mkdir()
        for suffix in ("json", "md", "srt"):
            (transcript_dir / f"transcript.{suffix}").write_text("result")
        complete_claim(self.config, claim, transcript_dir, duration_seconds=1.0, peak_gpu_memory_mb=10)
        self.assertTrue(processed_path(self.config, claim.recording).exists())
        with connect(self.config) as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id=?", (claim.job.id,)).fetchone()
            self.assertEqual(row[0], "complete")

    def _write_outputs(self, claim):
        transcript_dir = self.config.transcripts_dir / claim.recording.sha256
        transcript_dir.mkdir(exist_ok=True)
        for suffix in ("json", "md", "srt"):
            (transcript_dir / f"transcript.{suffix}").write_text("result")
        return transcript_dir

    def test_same_filename_completions_preserve_both_originals(self):
        first = claim_next(self.config)
        complete_claim(self.config, first, self._write_outputs(first), duration_seconds=None, peak_gpu_memory_mb=None)
        first_destination = processed_path(self.config, first.recording)
        (self.config.incoming_dir / "sample.mp3").write_bytes(b"different audio")
        second_recording = discover(self.config)[0]
        second = claim_next(self.config)
        complete_claim(self.config, second, self._write_outputs(second), duration_seconds=None, peak_gpu_memory_mb=None)
        second_destination = processed_path(self.config, second_recording)
        self.assertEqual(first_destination.read_bytes(), b"audio")
        self.assertEqual(second_destination.read_bytes(), b"different audio")
        self.assertNotEqual(first_destination, second_destination)

    def test_reconciles_expired_completion_after_source_move(self):
        claim = claim_next(self.config)
        transcript_dir = self._write_outputs(claim)
        destination = processed_path(self.config, claim.recording)
        claim.recording.current_path.replace(destination)
        with connect(self.config) as connection:
            connection.execute("UPDATE jobs SET claim_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (claim.job.id,))
        self.assertEqual(reconcile_interrupted_completions(self.config), 1)
        with connect(self.config) as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id=?", (claim.job.id,)).fetchone()
        self.assertEqual(row[0], "complete")
        self.assertTrue(destination.exists())

    def test_reconciles_expired_completion_after_transcript_publication(self):
        claim = claim_next(self.config)
        self._write_outputs(claim)
        with connect(self.config) as connection:
            connection.execute("UPDATE jobs SET claim_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (claim.job.id,))
        self.assertEqual(reconcile_interrupted_completions(self.config), 1)
        self.assertTrue(processed_path(self.config, claim.recording).exists())

    def test_partial_transcript_reconciliation_fails_job_and_allows_next_claim(self):
        first = claim_next(self.config)
        transcript_dir = self.config.transcripts_dir / first.recording.sha256
        transcript_dir.mkdir()
        (transcript_dir / "transcript.json").write_text("partial")
        with connect(self.config) as connection:
            connection.execute("UPDATE jobs SET claim_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (first.job.id,))
        (self.config.incoming_dir / "second.mp3").write_bytes(b"second")
        discover(self.config)
        self.assertEqual(reconcile_interrupted_completions(self.config), 0)
        with connect(self.config) as connection:
            failed = connection.execute("SELECT status, latest_error_step FROM jobs WHERE id=?", (first.job.id,)).fetchone()
        self.assertEqual(tuple(failed), ("failed", "completion_reconciliation"))
        second = claim_next(self.config)
        self.assertIsNotNone(second)
        self.assertNotEqual(second.job.id, first.job.id)


    def test_completion_refuses_lost_token(self):
        claim = claim_next(self.config)
        bad = type(claim)(claim.job, claim.recording, claim.attempt_id, "wrong")
        with self.assertRaises(DomainError):
            complete_claim(self.config, bad, self.config.transcripts_dir, duration_seconds=None, peak_gpu_memory_mb=None)

    def test_run_next_pulls_valid_result_completes_and_cleans(self):
        fixture = Path(__file__).parent / "fixtures" / "transcript_valid.json"

        class Finished:
            def poll(self):
                return 0

            def wait(self, timeout=None):
                return CommandResult(("ssh",), 0, "", "")

            def terminate(self):
                raise AssertionError("successful worker should not be terminated")

        class FakeRunner:
            def __init__(self):
                self.calls = []

            def run(self, args, *, secrets=()):
                self.calls.append(tuple(args))
                if args[0] == "scp" and ":" in args[1]:
                    target = Path(args[2])
                    document = json.loads(fixture.read_text())
                    with connect(self.config) as connection:
                        digest = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
                    document["recording"]["sha256"] = digest
                    target.write_text(json.dumps(document))
                return CommandResult(tuple(args), 0, "", "")

            def start(self, args, *, secrets=()):
                self.calls.append(tuple(args))
                return Finished()

        runner = FakeRunner()
        runner.config = self.config
        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}):
            result = run_next(self.config, runner=runner, sleep=lambda _: None)
        self.assertEqual(result["result"], "complete")
        self.assertTrue(any(call[0] == "scp" for call in runner.calls))
        self.assertTrue(any("rm -rf" in " ".join(call) for call in runner.calls))

    def test_heartbeat_renews_claim_while_worker_runs(self):
        fixture = Path(__file__).parent / "fixtures" / "transcript_valid.json"

        class Delayed:
            def __init__(self):
                self.polls = 0

            def poll(self):
                self.polls += 1
                return None if self.polls == 1 else 0

            def wait(self, timeout=None):
                return CommandResult(("ssh",), 0, "", "")

        class Runner:
            def run(inner_self, args, *, secrets=()):
                if args[0] == "scp" and ":" in args[1]:
                    target = Path(args[2])
                    document = json.loads(fixture.read_text())
                    with connect(self.config) as connection:
                        document["recording"]["sha256"] = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
                    target.write_text(json.dumps(document))
                return CommandResult(tuple(args), 0, "", "")

            def start(self, args, *, secrets=()):
                return Delayed()

        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}), patch(
            "field_transcriber.orchestrator.renew_claim", wraps=renew_claim
        ) as renew:
            result = run_next(self.config, runner=Runner(), sleep=lambda _: None)
        self.assertEqual(result["result"], "complete")
        self.assertGreaterEqual(renew.call_count, 2)

    def test_claim_loss_terminates_worker_and_records_cleanup(self):
        class Running:
            terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

        class Runner:
            def __init__(self):
                self.running = Running()

            def run(self, args, *, secrets=()):
                return CommandResult(tuple(args), 0, "", "")

            def start(self, args, *, secrets=()):
                return self.running

        runner = Runner()
        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}), patch(
            "field_transcriber.orchestrator.renew_claim", return_value=False
        ):
            with self.assertRaisesRegex(DomainError, "claim ownership"):
                run_next(self.config, runner=runner, sleep=lambda _: None)
        self.assertTrue(runner.running.terminated)
        with connect(self.config) as connection:
            attempt = connection.execute("SELECT cleanup_status FROM attempts").fetchone()
        self.assertEqual(attempt[0], "complete")

    def test_lost_claim_prevents_transcript_publication(self):
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
                    document = json.loads(fixture.read_text())
                    with connect(self.config) as connection:
                        document["recording"]["sha256"] = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
                    target.write_text(json.dumps(document))
                return CommandResult(tuple(args), 0, "", "")

            def start(self, args, *, secrets=()):
                return Finished()

        with patch.dict("os.environ", {"HF_TOKEN": "test-token"}), patch(
            "field_transcriber.orchestrator.assert_claim_owned", side_effect=DomainError("lost", step="claim_lost")
        ), patch("field_transcriber.orchestrator.publish_transcripts") as publish:
            with self.assertRaises(DomainError):
                run_next(self.config, runner=Runner())
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
