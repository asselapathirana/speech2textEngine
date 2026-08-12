import unittest
from datetime import UTC, datetime
import io
import tempfile
from pathlib import Path

from field_transcriber.object_store import ObjectStore


class ObjectStoreTests(unittest.TestCase):
    def test_presigned_url_is_scoped_and_deterministic(self):
        store = ObjectStore("https://objects.example", "bucket", "eu-west-1", "access", "secret")
        url = store.presign("GET", "attempts/1/recording.mp3", 600, now=datetime(2026, 1, 1, tzinfo=UTC))
        self.assertIn("/bucket/attempts/1/recording.mp3?", url)
        self.assertIn("X-Amz-Expires=600", url)
        self.assertIn("X-Amz-Signature=", url)
        self.assertNotIn("secret", url)

    def test_request_methods_cover_upload_download_head_and_delete(self):
        calls = []
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): return False
        def opener(request, timeout):
            calls.append((request.method, request.data))
            return Response(b"result" if request.method == "GET" else b"")
        store = ObjectStore("https://objects.example", "bucket", "eu-west-1", "access", "secret", opener=opener)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "audio.mp3"
            source.write_bytes(b"audio")
            store.upload("input", source)
        self.assertEqual(store.download("result"), b"result")
        self.assertTrue(store.exists("result"))
        store.delete("result")
        self.assertEqual([method for method, _ in calls], ["PUT", "GET", "HEAD", "DELETE"])
        self.assertEqual(calls[0][1], b"audio")


if __name__ == "__main__":
    unittest.main()
