import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from field_transcriber.config import Config
from field_transcriber.db import connect, initialize
from field_transcriber.jobs import claim_next, quarantine_job, recover_expired_claims, retry_job
from field_transcriber.models import DomainError
from field_transcriber.recordings import discover


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Config(root=Path(self.temp.name), worker_host="worker")
        initialize(self.config)
        (self.config.incoming_dir / "sample.mp3").write_bytes(b"audio")
        discover(self.config)

    def test_expired_claim_becomes_failed_with_error(self):
        claim = claim_next(self.config)
        expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        with connect(self.config) as connection:
            connection.execute("UPDATE jobs SET claim_expires_at=? WHERE id=?", (expired, claim.job.id))
            connection.commit()
        self.assertEqual(recover_expired_claims(self.config), 1)
        with connect(self.config) as connection:
            row = connection.execute("SELECT status, latest_error_step FROM jobs WHERE id=?", (claim.job.id,)).fetchone()
            self.assertEqual(tuple(row), ("failed", "claim_expired"))

    def test_failed_job_can_retry_but_complete_or_quarantined_cannot(self):
        claim = claim_next(self.config)
        with connect(self.config) as connection:
            connection.execute("UPDATE jobs SET status='failed', claim_token=NULL, claim_expires_at=NULL WHERE id=?", (claim.job.id,))
            connection.commit()
        retry_job(self.config, claim.job.id)
        with self.assertRaises(DomainError):
            retry_job(self.config, claim.job.id)
        new_claim = claim_next(self.config)
        with connect(self.config) as connection:
            connection.execute("UPDATE jobs SET status='failed', claim_token=NULL, claim_expires_at=NULL WHERE id=?", (new_claim.job.id,))
            connection.commit()
        quarantine_job(self.config, new_claim.job.id, "not useful")
        self.assertTrue((self.config.failed_dir / "sample.mp3").exists())
        with self.assertRaises(DomainError):
            retry_job(self.config, new_claim.job.id)


if __name__ == "__main__":
    unittest.main()
