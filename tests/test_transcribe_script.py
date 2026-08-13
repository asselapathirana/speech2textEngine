import importlib.util
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("local_transcribe", Path(__file__).parents[1] / "local" / "transcribe.py")
transcribe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(transcribe)


class TranscribeScriptTests(unittest.TestCase):
    def test_load_env_ignores_comments_and_unquotes_values(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.env"
            config.write_text("# local settings\nHOST='hpd'\nEMPTY=\n")
            self.assertEqual(transcribe.load_env(config), {"HOST": "hpd", "EMPTY": ""})

    def test_select_job_rejects_another_active_queue_item(self):
        jobs = [
            {"id": 1, "sha256": "older", "status": "pending"},
            {"id": 2, "sha256": "target", "status": "pending"},
        ]
        with self.assertRaisesRegex(RuntimeError, "another queued job"):
            transcribe.select_job(jobs, "target")

    def test_completed_job_can_be_downloaded_despite_queue(self):
        jobs = [
            {"id": 1, "sha256": "target", "status": "complete"},
            {"id": 2, "sha256": "other", "status": "processing"},
        ]
        self.assertEqual(transcribe.select_job(jobs, "target")["id"], 1)

    def test_remote_name_sanitizes_spaces_without_changing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "field recording.mp3"
            source.write_bytes(b"audio")
            transcribe.validate_source(source)
            self.assertEqual(transcribe.remote_name(source, "a" * 64), "field_recording-aaaaaaaaaaaa.mp3")

    def test_resolve_sources_expands_wildcards_and_removes_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a one.mp3"
            second = root / "b.mp3"
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            sources = transcribe.resolve_sources([str(root / "*.mp3"), str(first)])
            self.assertEqual(sources, [first.resolve(), second.resolve()])

    def test_resolve_sources_reports_unmatched_pattern(self):
        with self.assertRaisesRegex(ValueError, "no files matched"):
            transcribe.resolve_sources(["/definitely/missing/*.mp3"])


if __name__ == "__main__":
    unittest.main()
