import json
import tempfile
import unittest
from pathlib import Path

from field_transcriber.renderers import render_markdown, render_srt, publish_transcripts


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((Path(__file__).parent / "fixtures/transcript_valid.json").read_text())

    def test_markdown_contains_speaker_timestamp_and_text(self):
        output = render_markdown(self.document)
        self.assertIn("SPEAKER_01", output)
        self.assertIn("00:00:00.500", output)
        self.assertIn("Hello field team.", output)

    def test_srt_contains_numbered_timed_cue(self):
        output = render_srt(self.document)
        self.assertIn("1\n00:00:00,500 --> 00:00:02,000", output)
        self.assertIn("[SPEAKER_01] Hello field team.", output)

    def test_unknown_speaker_is_preserved_as_unknown(self):
        document = json.loads(json.dumps(self.document))
        document["segments"][0]["speaker"] = None
        self.assertIn("UNKNOWN", render_markdown(document))

    def test_atomic_publication_writes_three_nonempty_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = publish_transcripts(self.document, Path(directory), "a" * 64)
            self.assertEqual({p.suffix for p in paths}, {".json", ".md", ".srt"})
            self.assertTrue(all(p.stat().st_size > 0 for p in paths))


if __name__ == "__main__":
    unittest.main()
