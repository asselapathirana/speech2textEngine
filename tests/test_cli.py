import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from field_transcriber.cli import main
from field_transcriber.config import Config
from field_transcriber.db import initialize
from field_transcriber.jobs import claim_next
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


if __name__ == "__main__":
    unittest.main()
