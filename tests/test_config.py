import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from field_transcriber.config import Config, ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def test_defaults_create_expected_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(root=Path(directory))
            self.assertEqual(config.db_path, Path(directory) / "state" / "jobs.db")
            self.assertEqual(config.lease_seconds, 300)
            self.assertEqual(config.heartbeat_seconds, 60)

    def test_heartbeat_must_be_shorter_than_lease(self):
        with self.assertRaises(ConfigError):
            Config(root=Path("/tmp/field-test"), lease_seconds=60, heartbeat_seconds=60)

    def test_load_config_file_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.env"
            path.write_text(
                "FIELD_TRANSCRIBER_ROOT=/tmp/from-file\n"
                "FIELD_TRANSCRIBER_CLAIM_LEASE_SECONDS=600\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"FIELD_TRANSCRIBER_ROOT": "/tmp/from-env"}):
                config = load_config(path)
            self.assertEqual(config.root, Path("/tmp/from-env"))
            self.assertEqual(config.lease_seconds, 600)

    def test_rejects_unknown_config_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.env"
            path.write_text("FIELD_TRANSCRIBER_UNKNOWN=value\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
