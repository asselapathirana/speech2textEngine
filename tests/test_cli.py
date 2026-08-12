import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from field_transcriber.cli import main
from field_transcriber.config import Config
from field_transcriber.db import initialize
from field_transcriber.jobs import claim_next, processed_path
from field_transcriber.recordings import discover


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_init_json_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.env"
            config.write_text(f"FIELD_TRANSCRIBER_ROOT={directory}/files\n")
            code, stdout, stderr = self.invoke("--config", str(config), "init", "--json")
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual(json.loads(stdout)["result"], "initialized")

    def test_configuration_failure_is_usage_error(self):
        code, stdout, stderr = self.invoke("--config", "/missing/config.env", "init")
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("configuration", stderr.lower())

    def test_status_never_exposes_claim_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "files"
            config_path = Path(directory) / "config.env"
            config_path.write_text(f"FIELD_TRANSCRIBER_ROOT={root}\nFIELD_TRANSCRIBER_WORKER_HOST=worker\n")
            config = Config(root=root, worker_host="worker")
            initialize(config)
            (config.incoming_dir / "sample.mp3").write_bytes(b"audio")
            discover(config)
            claim_next(config)
            code, stdout, _ = self.invoke("--config", str(config_path), "status", "--json")
            self.assertEqual(code, 0)
            self.assertNotIn("claim_token", stdout)
            self.assertIn("claim_expires_at", stdout)

    def test_status_filters_by_job_or_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "files"
            config_path = Path(directory) / "config.env"
            config_path.write_text(f"FIELD_TRANSCRIBER_ROOT={root}\n")
            config = Config(root=root)
            initialize(config)
            (config.incoming_dir / "one.mp3").write_bytes(b"one")
            first = discover(config)[0]
            (config.incoming_dir / "two.mp3").write_bytes(b"two")
            discover(config)
            code, stdout, _ = self.invoke("--config", str(config_path), "status", "--recording", first.sha256, "--json")
            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["count"], 1)
            job_id = payload["jobs"][0]["id"]
            code, stdout, _ = self.invoke("--config", str(config_path), "status", "--job", str(job_id), "--json")
            self.assertEqual(json.loads(stdout)["count"], 1)

    def test_config_defaults_to_config_env(self):
        parser = __import__("field_transcriber.cli", fromlist=["build_parser"]).build_parser()
        args = parser.parse_args(["status"])
        self.assertEqual(args.config, Path("config.env"))

    def test_remote_owner_commands_parse(self):
        parser = __import__("field_transcriber.cli", fromlist=["build_parser"]).build_parser()
        self.assertEqual(parser.parse_args(["cancel", "--job", "3"]).job, 3)
        self.assertEqual(parser.parse_args(["resolve-remote", "--job", "3", "--decision", "wait"]).decision, "wait")
        self.assertEqual(parser.parse_args(["cleanup-transfers"]).command, "cleanup-transfers")

    def test_run_next_reconciles_before_expired_claim_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "files"
            config_path = Path(directory) / "config.env"
            config_path.write_text(f"FIELD_TRANSCRIBER_ROOT={root}\n")
            config = Config(root=root)
            initialize(config)
            (config.incoming_dir / "sample.mp3").write_bytes(b"audio")
            discover(config)
            claim = claim_next(config)
            transcript_dir = config.transcripts_dir / claim.recording.sha256
            transcript_dir.mkdir()
            for suffix in ("json", "md", "srt"):
                (transcript_dir / f"transcript.{suffix}").write_text("result")
            claim.recording.current_path.replace(processed_path(config, claim.recording))
            with __import__("field_transcriber.db", fromlist=["connect"]).connect(config) as connection:
                connection.execute("UPDATE jobs SET claim_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (claim.job.id,))
            code, stdout, stderr = self.invoke("--config", str(config_path), "run-next", "--json")
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual(json.loads(stdout)["result"], "no_job")
            with __import__("field_transcriber.db", fromlist=["connect"]).connect(config) as connection:
                status = connection.execute("SELECT status FROM jobs WHERE id=?", (claim.job.id,)).fetchone()[0]
            self.assertEqual(status, "complete")

    def test_runpod_restart_result_reconciliation_runs_through_main(self):
        from tests.test_remote import FakeProvider, MemoryStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "files"
            config_path = Path(directory) / "config.env"
            config_path.write_text(
                f"FIELD_TRANSCRIBER_ROOT={root}\nFIELD_TRANSCRIBER_WORKER_MODE=runpod\n"
                "FIELD_TRANSCRIBER_RUNPOD_ENDPOINT_ID=endpoint\nFIELD_TRANSCRIBER_OBJECT_STORE_ENDPOINT=https://objects.example\n"
                "FIELD_TRANSCRIBER_OBJECT_STORE_BUCKET=bucket\n"
            )
            config = Config(root=root, worker_mode="runpod", runpod_endpoint_id="endpoint", object_store_endpoint="https://objects.example", object_store_bucket="bucket")
            initialize(config)
            (config.incoming_dir / "sample.mp3").write_bytes(b"audio")
            discover(config)
            provider, store = FakeProvider(), MemoryStore()
            from field_transcriber.orchestrator import run_next
            run_next(config, provider=provider, store=store, sleep=None)
            from field_transcriber.db import connect
            with connect(config) as connection:
                digest = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
                key = connection.execute("SELECT result_reference FROM remote_executions").fetchone()[0]
            document = json.loads((Path(__file__).parent / "fixtures" / "transcript_valid.json").read_text())
            document["recording"]["sha256"] = digest
            store.objects[key] = json.dumps(document).encode()
            with patch("field_transcriber.orchestrator._remote_dependencies", return_value=(provider, store)):
                code, stdout, stderr = self.invoke("--config", str(config_path), "run-next", "--json")
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual(json.loads(stdout)["result"], "complete")
            self.assertEqual(len(provider.submissions), 1)


if __name__ == "__main__":
    unittest.main()
