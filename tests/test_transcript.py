import json
import unittest
from pathlib import Path

from field_transcriber.models import DomainError
from field_transcriber.transcript import validate_transcript


FIXTURES = Path(__file__).parent / "fixtures"


class TranscriptTests(unittest.TestCase):
    def load(self, name):
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def test_accepts_valid_contract(self):
        document = self.load("transcript_valid.json")
        validate_transcript(document, "a" * 64)

    def test_rejects_wrong_recording_digest(self):
        with self.assertRaises(DomainError):
            validate_transcript(self.load("transcript_valid.json"), "c" * 64)

    def test_speechless_has_specific_error(self):
        with self.assertRaises(DomainError) as caught:
            validate_transcript(self.load("transcript_speechless.json"), "b" * 64)
        self.assertEqual(caught.exception.step, "no_speech_detected")

    def test_rejects_reverse_and_out_of_order_times(self):
        document = self.load("transcript_valid.json")
        document["segments"][0]["end"] = 0.1
        with self.assertRaises(DomainError):
            validate_transcript(document, "a" * 64)

    def test_rejects_malformed_contract(self):
        with self.assertRaises(DomainError):
            validate_transcript(self.load("transcript_malformed.json"), "a" * 64)


if __name__ == "__main__":
    unittest.main()
