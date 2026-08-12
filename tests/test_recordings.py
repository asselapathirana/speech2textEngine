import hashlib
import tempfile
import unittest
from pathlib import Path

from field_transcriber.config import Config
from field_transcriber.db import connect, initialize
from field_transcriber.models import DomainError
from field_transcriber.recordings import discover, publish_upload


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(root=Path(self.temp.name))
        initialize(self.config)

    def stage(self, name="sample.mp3.partial", content=b"field audio"):
        path = self.config.uploading_dir / name
        path.write_bytes(content)
        return path, hashlib.sha256(content).hexdigest()

    def test_verified_upload_is_published_and_registered_once(self):
        staged, digest = self.stage()
        first = publish_upload(self.config, staged.name, "sample.mp3", staged.stat().st_size, digest)
        self.assertEqual(first.sha256, digest)
        self.assertEqual(first.current_path, self.config.incoming_dir / "sample.mp3")
        duplicate, _ = self.stage("again.partial")
        second = publish_upload(self.config, duplicate.name, "renamed.mp3", duplicate.stat().st_size, digest)
        self.assertEqual(second.id, first.id)
        with connect(self.config) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM recordings").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

    def test_incomplete_upload_remains_staged(self):
        staged, digest = self.stage()
        with self.assertRaises(DomainError):
            publish_upload(self.config, staged.name, "sample.mp3", staged.stat().st_size + 1, digest)
        self.assertTrue(staged.exists())
        self.assertEqual(list(self.config.incoming_dir.iterdir()), [])

    def test_filename_collision_with_different_digest_is_rejected(self):
        first, digest = self.stage(content=b"first")
        publish_upload(self.config, first.name, "sample.mp3", 5, digest)
        second, second_digest = self.stage("second.partial", b"second")
        with self.assertRaises(DomainError):
            publish_upload(self.config, second.name, "sample.mp3", 6, second_digest)
        self.assertEqual((self.config.incoming_dir / "sample.mp3").read_bytes(), b"first")

    def test_discovery_ignores_uploading_and_is_idempotent(self):
        self.stage()
        direct = self.config.incoming_dir / "direct.mp3"
        direct.write_bytes(b"direct")
        self.assertEqual(len(discover(self.config)), 1)
        self.assertEqual(len(discover(self.config)), 1)
        with connect(self.config) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
