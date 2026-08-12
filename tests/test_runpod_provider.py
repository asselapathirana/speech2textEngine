import io
import json
import unittest

from field_transcriber.remote import RemoteRequest
from field_transcriber.runpod_provider import RunpodProvider


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): return False


class RunpodProviderTests(unittest.TestCase):
    def test_submit_maps_queue_state_and_contract(self):
        captured = {}
        def opener(request, timeout):
            captured["document"] = json.loads(request.data)
            return Response(b'{"id":"remote-1","status":"IN_QUEUE"}')
        provider = RunpodProvider("endpoint", "secret", opener=opener)
        request = RemoteRequest("x" * 24, "a" * 64, "audio.mp3", "https://get", "https://put", 7200000, 10800000)
        status = provider.submit(request)
        self.assertEqual((status.state, status.external_job_id), ("queued", "remote-1"))
        self.assertEqual(captured["document"]["policy"]["executionTimeout"], 7200000)

    def test_unknown_status_is_indeterminate(self):
        provider = RunpodProvider("endpoint", "secret")
        self.assertEqual(provider._status({"status": "NEW"}).state, "indeterminate")


if __name__ == "__main__":
    unittest.main()
