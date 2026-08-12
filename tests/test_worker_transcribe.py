import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from worker.transcribe import normalize_result, transcribe


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
        document = normalize_result(raw, "a" * 64, "sample.mp3", language_code="en", language_confidence=0.9, duration_seconds=2.0, peak_gpu_memory_mb=None)
        self.assertEqual(document["segments"][0]["text"], "hello")
        self.assertIsNone(document["segments"][0]["speaker"])
        self.assertIsNone(document["segments"][0]["words"][0]["confidence"])
        self.assertEqual(document["run"]["model"], "large-v3")
        self.assertEqual(document["language"], {"code": "en", "confidence": 0.9})

    def test_transcribe_preserves_language_before_alignment(self):
        class Model:
            def transcribe(self, audio, batch_size):
                return {
                    "language": "nl",
                    "language_probability": 0.87,
                    "segments": [{"start": 0.0, "end": 1.0, "text": "Hallo", "words": []}],
                }

        whisperx = ModuleType("whisperx")
        whisperx.load_audio = lambda path: "audio"
        whisperx.load_model = lambda *args, **kwargs: Model()
        whisperx.load_align_model = lambda **kwargs: ("align", {})
        whisperx.align = lambda segments, *args, **kwargs: {"segments": segments}
        whisperx.assign_word_speakers = lambda diarization, result: result
        diarize = ModuleType("whisperx.diarize")
        diarize.DiarizationPipeline = lambda **kwargs: lambda audio: "speakers"
        torch = SimpleNamespace(
            cuda=SimpleNamespace(reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)
        )
        with patch.dict("sys.modules", {"torch": torch, "whisperx": whisperx, "whisperx.diarize": diarize}):
            document = transcribe(Path("sample.mp3"), "sample.mp3", "a" * 64, "token")
        self.assertEqual(document["language"], {"code": "nl", "confidence": 0.87})


if __name__ == "__main__":
    unittest.main()
