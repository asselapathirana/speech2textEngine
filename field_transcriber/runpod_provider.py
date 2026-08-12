"""Runpod queue API adapter isolated from controller domain logic."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .remote import RemoteRequest, RemoteStatus, bounded_diagnostic

STATE_MAP = {
    "IN_QUEUE": "queued", "IN_PROGRESS": "running", "COMPLETED": "succeeded",
    "FAILED": "failed", "CANCELLED": "cancelled", "TIMED_OUT": "expired",
}


class RunpodProvider:
    def __init__(self, endpoint_id: str, api_key: str, *, opener=urllib.request.urlopen, sleep=time.sleep):
        self.base = f"https://api.runpod.ai/v2/{endpoint_id}"
        self.api_key = api_key
        self.opener = opener
        self.sleep = sleep

    def _call(self, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base + path, data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        for attempt in range(3):
            try:
                with self.opener(request, timeout=30) as response:
                    return json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code != 429 and exc.code < 500:
                    raise
                if attempt == 2:
                    raise
                self.sleep(2**attempt)

    def _status(self, document: dict, fallback_id: str | None = None) -> RemoteStatus:
        external_id = document.get("id") or fallback_id
        state = STATE_MAP.get(document.get("status"), "indeterminate")
        diagnostic = document.get("error")
        return RemoteStatus(state, external_id, bounded_diagnostic(diagnostic, (self.api_key,)) if diagnostic else None, document.get("output"))

    def submit(self, request: RemoteRequest) -> RemoteStatus:
        payload = {
            "input": {
                "idempotency_key": request.idempotency_key, "recording_sha256": request.recording_sha256,
                "original_name": request.original_name, "input_url": request.input_url, "result_url": request.result_url,
            },
            "policy": {"executionTimeout": request.execution_timeout_ms, "ttl": request.ttl_ms},
        }
        try:
            return self._status(self._call("/run", payload))
        except (OSError, ValueError) as exc:
            return RemoteStatus("indeterminate", diagnostic=bounded_diagnostic(exc, (self.api_key,)))

    def status(self, external_job_id: str) -> RemoteStatus:
        try:
            return self._status(self._call(f"/status/{external_job_id}"), external_job_id)
        except (OSError, ValueError) as exc:
            return RemoteStatus("indeterminate", external_job_id, bounded_diagnostic(exc, (self.api_key,)))

    def cancel(self, external_job_id: str) -> RemoteStatus:
        try:
            return self._status(self._call(f"/cancel/{external_job_id}", {}), external_job_id)
        except (OSError, ValueError) as exc:
            return RemoteStatus("indeterminate", external_job_id, bounded_diagnostic(exc, (self.api_key,)))
