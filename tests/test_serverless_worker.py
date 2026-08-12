import hashlib
import io
import json
import unittest
from unittest.mock import patch

from worker import serverless


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): return False


class ServerlessWorkerTests(unittest.TestCase):
    def test_handler_checks_digest_and_uploads_canonical_json(self):
        audio = b"audio"
        uploaded = {}
        def opener(request, timeout):
            if isinstance(request, str): return Response(audio)
            uploaded["body"] = request.data
            return Response(b"")
        document = {"recording": {"sha256": hashlib.sha256(audio).hexdigest()}, "run": {"duration_seconds": 1}}
        event = {"input": {"idempotency_key": "key", "recording_sha256": hashlib.sha256(audio).hexdigest(), "original_name": "sample.mp3", "input_url": "https://get", "result_url": "https://put"}}
        with patch.dict("os.environ", {"HF_TOKEN": "token"}), patch("worker.serverless.urllib.request.urlopen", side_effect=opener), patch("worker.serverless.transcribe", return_value=document):
            manifest = serverless.handler(event)
        self.assertEqual(json.loads(uploaded["body"]), document)
        self.assertEqual(manifest["recording_sha256"], event["input"]["recording_sha256"])

    def test_module_import_does_not_require_runpod_sdk(self):
        self.assertTrue(callable(serverless.handler))


if __name__ == "__main__":
    unittest.main()
