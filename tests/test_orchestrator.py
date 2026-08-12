import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from field_transcriber.config import Config
from field_transcriber.db import connect, initialize
from field_transcriber.jobs import claim_next, complete_claim, renew_claim
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

    def test_completion_requires_owned_claim_and_moves_source(self):
        claim = claim_next(self.config)
        transcript_dir = self.config.transcripts_dir / claim.recording.sha256
        transcript_dir.mkdir()
        for suffix in ("json", "md", "srt"):
            (transcript_dir / f"transcript.{suffix}").write_text("result")
        complete_claim(self.config, claim, transcript_dir, duration_seconds=1.0, peak_gpu_memory_mb=10)
        self.assertTrue((self.config.processed_dir / "sample.mp3").exists())
        with connect(self.config) as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id=?", (claim.job.id,)).fetchone()
            self.assertEqual(row[0], "complete")

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


if __name__ == "__main__":
    unittest.main()
