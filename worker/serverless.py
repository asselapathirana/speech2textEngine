"""Runpod handler around the provider-neutral transcription operation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request
import os

from worker.transcribe import transcribe


def handler(event: dict) -> dict:
    payload = event.get("input", {})
    required = {"idempotency_key", "recording_sha256", "original_name", "input_url", "result_url"}
    if not required <= payload.keys():
        raise ValueError("serverless request is missing required input fields")
    with tempfile.TemporaryDirectory(prefix="field-transcriber-worker-") as directory:
        source = Path(directory) / "recording.mp3"
        with urllib.request.urlopen(payload["input_url"], timeout=300) as response:
            source.write_bytes(response.read())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != payload["recording_sha256"]:
            raise ValueError("recording digest mismatch")
        token = os.environ.get("HF_TOKEN", "")
        if not token:
            raise ValueError("HF_TOKEN is required")
        document = transcribe(source, payload["original_name"], digest, token)
        body = json.dumps(document, sort_keys=True).encode()
        request = urllib.request.Request(payload["result_url"], data=body, method="PUT", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=300):
            pass
        return {"recording_sha256": digest, "result_sha256": hashlib.sha256(body).hexdigest(), "run": document.get("run", {})}


def start() -> None:
    import runpod

    runpod.serverless.start({"handler": handler})


if __name__ == "__main__":
    start()
