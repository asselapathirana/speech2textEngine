import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class UploadScriptTests(unittest.TestCase):
    def test_script_uses_resumable_staging_and_publish_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.mp3"
            source.write_bytes(b"audio")
            log = root / "calls.log"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            for name in ("rsync", "ssh"):
                script = fake_bin / name
                script.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$0 $*\" >> '{log}'\n", encoding="utf-8")
                script.chmod(0o755)
            config = root / "config.env"
            config.write_text(
                "FIELD_TRANSCRIBER_VPS_HOST=vps.test\n"
                "FIELD_TRANSCRIBER_VPS_USER=assela\n"
                "FIELD_TRANSCRIBER_VPS_CODE=/home/assela/field-transcriber/code\n"
                "FIELD_TRANSCRIBER_VPS_FILES=/home/assela/field-transcriber/files\n"
                "FIELD_TRANSCRIBER_VPS_PYTHON=python3\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env['PATH']}"
            env["FIELD_TRANSCRIBER_UPLOAD_CONFIG"] = str(config)
            result = subprocess.run(["sh", "local/upload.sh", str(source)], cwd=Path(__file__).parents[1], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text()
            self.assertIn("--partial", calls)
            self.assertIn("uploading/sample.mp3.partial", calls)
            self.assertIn("publish-upload", calls)
            self.assertIn("--sha256", calls)
            repeated = subprocess.run(["sh", "local/upload.sh", str(source)], cwd=Path(__file__).parents[1], env=env, text=True, capture_output=True)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(log.read_text().count("publish-upload"), 2)


if __name__ == "__main__":
    unittest.main()
