import unittest

from worker.transcribe import normalize_result


class WorkerNormalizationTests(unittest.TestCase):
    def test_normalizes_whisperx_result_and_preserves_missing_values(self):
        raw = {
            "language": "en",
            "segments": [{
                "start": 0.0,
                "end": 1.0,
                "speaker": None,
                "text": " hello ",
                "words": [{"word": "hello", "start": 0.0, "end": 1.0, "score": None}],
            }],
        }
        document = normalize_result(raw, "a" * 64, "sample.mp3", duration_seconds=2.0, peak_gpu_memory_mb=None)
        self.assertEqual(document["segments"][0]["text"], "hello")
        self.assertIsNone(document["segments"][0]["speaker"])
        self.assertIsNone(document["segments"][0]["words"][0]["confidence"])
        self.assertEqual(document["run"]["model"], "large-v3")


if __name__ == "__main__":
    unittest.main()
