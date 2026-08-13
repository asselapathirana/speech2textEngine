import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from field_transcriber.config import Config
from field_transcriber.db import connect, initialize
from field_transcriber.orchestrator import run_next
from field_transcriber.recordings import discover
from field_transcriber.remote import RemoteStatus
from field_transcriber.remote import cancel_remote, cleanup_transfers, resolve_remote
from field_transcriber.jobs import claim_next, retry_job
from datetime import UTC, datetime, timedelta


class MemoryStore:
    def __init__(self): self.objects = {}
    def upload(self, key, path): self.objects[key] = path.read_bytes()
    def download(self, key): return self.objects[key]
    def exists(self, key): return key in self.objects
    def delete(self, key): self.objects.pop(key, None)
    def presign(self, method, key, expires): return f"https://objects.example/{key}?method={method}"


class FakeProvider:
    def __init__(self): self.submissions = []; self.next_status = RemoteStatus("queued", "remote-1")
    def submit(self, request): self.submissions.append(request); return RemoteStatus("queued", "remote-1")
    def status(self, external_job_id): return self.next_status
    def cancel(self, external_job_id): self.next_status = RemoteStatus("cancelled", external_job_id); return self.next_status


class RemoteLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.config = Config(root=Path(self.temp.name), worker_mode="runpod", runpod_endpoint_id="endpoint", object_store_endpoint="https://objects.example", object_store_bucket="bucket")
        initialize(self.config)
        (self.config.incoming_dir / "sample.mp3").write_bytes(b"audio")
        discover(self.config)
        self.provider, self.store = FakeProvider(), MemoryStore()

    def test_submit_persists_identity_and_does_not_duplicate(self):
        first = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        second = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(first["external_job_id"], "remote-1")
        self.assertEqual(second["result"], "remote_active")
        self.assertEqual(len(self.provider.submissions), 1)
        with connect(self.config) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM remote_executions").fetchone()[0], 1)

    def test_result_object_completes_even_if_status_is_indeterminate(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        with connect(self.config) as connection:
            digest = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
            result_key = connection.execute("SELECT result_reference FROM remote_executions").fetchone()[0]
        document = json.loads((Path(__file__).parent / "fixtures" / "transcript_valid.json").read_text())
        document["recording"]["sha256"] = digest
        self.store.objects[result_key] = json.dumps(document).encode()
        self.provider.next_status = RemoteStatus("indeterminate", "remote-1")
        result = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(result["result"], "complete")
        self.assertFalse(self.store.objects)

    def test_invalid_result_falls_through_to_provider_without_new_submission(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        with connect(self.config) as connection:
            key = connection.execute("SELECT result_reference FROM remote_executions").fetchone()[0]
        self.store.objects[key] = b"not json"
        result = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(result["result"], "remote_active")
        self.assertEqual(len(self.provider.submissions), 1)

    def test_succeeded_status_waits_for_eventually_visible_result(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.provider.next_status = RemoteStatus("succeeded", "remote-1")
        result = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(result["result"], "remote_active")
        with connect(self.config) as connection:
            row = connection.execute("SELECT status, latest_error_step FROM jobs").fetchone()
        self.assertEqual(tuple(row), ("processing", None))

    def test_retry_ignores_historical_failed_remote_execution(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.provider.next_status = RemoteStatus("failed", "remote-1", "first attempt failed")
        self.assertEqual(run_next(self.config, provider=self.provider, store=self.store, sleep=None)["result"], "failed")
        with connect(self.config) as connection:
            job_id = connection.execute("SELECT id FROM jobs").fetchone()[0]
        retry_job(self.config, job_id)
        self.provider.next_status = RemoteStatus("queued", "remote-2")
        self.provider.submit = lambda request: (self.provider.submissions.append(request) or RemoteStatus("queued", "remote-2"))
        submitted = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(submitted.get("external_job_id"), "remote-2", submitted)
        with connect(self.config) as connection:
            digest = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
            key = connection.execute("SELECT result_reference FROM remote_executions ORDER BY id DESC").fetchone()[0]
        document = json.loads((Path(__file__).parent / "fixtures" / "transcript_valid.json").read_text())
        document["recording"]["sha256"] = digest
        self.store.objects[key] = json.dumps(document).encode()
        self.provider.next_status = RemoteStatus("succeeded", "remote-2")
        self.assertEqual(run_next(self.config, provider=self.provider, store=self.store, sleep=None)["result"], "complete")

    def test_owner_can_abandon_indeterminate_after_deadline(self):
        self.provider.submit = lambda request: RemoteStatus("indeterminate")
        result = run_next(self.config, provider=self.provider, store=self.store)
        with connect(self.config) as connection:
            connection.execute("UPDATE remote_executions SET reconcile_after='2000-01-01T00:00:00+00:00'")
        resolved = resolve_remote(self.config, result["job_id"], "abandon-retry")
        self.assertEqual(resolved["result"], "abandon_retry")

    def test_cleanup_retries_failed_objects(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        with connect(self.config) as connection:
            connection.execute("UPDATE transfer_objects SET state='cleanup_failed'")
        outcomes = cleanup_transfers(self.config, self.store)
        self.assertTrue(outcomes)
        self.assertTrue(all(item["state"] == "deleted" for item in outcomes))

    def test_valid_result_wins_cancellation_race(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        with connect(self.config) as connection:
            digest = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
            key = connection.execute("SELECT result_reference FROM remote_executions").fetchone()[0]
            job_id = connection.execute("SELECT id FROM jobs").fetchone()[0]
        document = json.loads((Path(__file__).parent / "fixtures" / "transcript_valid.json").read_text())
        document["recording"]["sha256"] = digest
        self.store.objects[key] = json.dumps(document).encode()
        result = cancel_remote(self.config, self.provider, self.store, job_id)
        self.assertEqual(result["result"], "complete")

    def test_failed_attempt_objects_delete_after_retention(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.provider.next_status = RemoteStatus("failed", "remote-1", "worker failed")
        result = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(result["result"], "failed")
        with connect(self.config) as connection:
            self.assertTrue(all(row[0] for row in connection.execute("SELECT retain_until FROM transfer_objects")))
            connection.execute("UPDATE transfer_objects SET retain_until='2000-01-01T00:00:00+00:00'")
        cleanup_transfers(self.config, self.store)
        self.assertFalse(self.store.objects)
        self.assertEqual(cleanup_transfers(self.config, self.store), [])

    def test_transient_result_probe_error_records_diagnostic_and_keeps_active(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.store.exists = lambda key: (_ for _ in ()).throw(OSError("store offline"))
        result = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(result["result"], "remote_active")
        with connect(self.config) as connection:
            diagnostic = connection.execute("SELECT diagnostic FROM remote_executions").fetchone()[0]
        self.assertIn("store offline", diagnostic)

    def test_upload_failure_is_retryable_failure_not_indeterminate(self):
        self.store.upload = lambda key, path: (_ for _ in ()).throw(OSError("upload failed"))
        result = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual((result["result"], result["remote_state"]), ("failed", "failed"))
        with connect(self.config) as connection:
            row = connection.execute("SELECT status, latest_error_step FROM jobs").fetchone()
        self.assertEqual(tuple(row), ("failed", "transfer_upload"))

    def test_runpod_mode_recovers_expired_claim_without_remote_execution(self):
        claim = claim_next(self.config)
        with connect(self.config) as connection:
            connection.execute("UPDATE jobs SET claim_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (claim.job.id,))
        result = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(result["result"], "no_job")
        with connect(self.config) as connection:
            self.assertEqual(connection.execute("SELECT status FROM jobs").fetchone()[0], "failed")

    def test_completion_failure_keeps_result_objects_for_reconciliation(self):
        run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        with connect(self.config) as connection:
            digest = connection.execute("SELECT sha256 FROM recordings").fetchone()[0]
            key = connection.execute("SELECT result_reference FROM remote_executions").fetchone()[0]
        document = json.loads((Path(__file__).parent / "fixtures" / "transcript_valid.json").read_text())
        document["recording"]["sha256"] = digest
        self.store.objects[key] = json.dumps(document).encode()
        from field_transcriber.models import DomainError
        with patch("field_transcriber.remote.complete_claim", side_effect=DomainError("database busy", step="completion")):
            result = run_next(self.config, provider=self.provider, store=self.store, sleep=None)
        self.assertEqual(result["result"], "remote_active")
        self.assertIn(key, self.store.objects)


if __name__ == "__main__":
    unittest.main()
