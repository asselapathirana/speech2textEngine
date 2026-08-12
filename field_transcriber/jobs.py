"""Durable recording/job operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import os
import secrets

from .config import Config
from .db import connect, transaction
from .models import Claim, DomainError, Job, Recording


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _recording(row) -> Recording:
    return Recording(row["id"], row["sha256"], row["original_name"], row["size_bytes"], row["status"], Path(row["current_path"]))


def _job(row) -> Job:
    return Job(row["id"], row["recording_id"], row["status"], row["attempt_count"], row["claim_token"], row["claim_expires_at"])


def find_recording_by_digest(config: Config, digest: str) -> Recording | None:
    with connect(config) as connection:
        row = connection.execute("SELECT * FROM recordings WHERE sha256 = ?", (digest,)).fetchone()
    return _recording(row) if row else None


def register_recording(config: Config, digest: str, name: str, size: int, path: Path) -> Recording:
    now = utc_now()
    with transaction(config, immediate=True) as connection:
        existing = connection.execute("SELECT * FROM recordings WHERE sha256 = ?", (digest,)).fetchone()
        if existing:
            return _recording(existing)
        cursor = connection.execute(
            "INSERT INTO recordings (sha256, original_name, size_bytes, status, current_path, ingested_at, updated_at) VALUES (?, ?, ?, 'incoming', ?, ?, ?)",
            (digest, name, size, str(path), now, now),
        )
        recording_id = cursor.lastrowid
        connection.execute(
            "INSERT INTO jobs (recording_id, status, attempt_count, created_at, updated_at) VALUES (?, 'pending', 0, ?, ?)",
            (recording_id, now, now),
        )
        row = connection.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
        return _recording(row)


def list_jobs(config: Config) -> list[dict]:
    with connect(config) as connection:
        rows = connection.execute(
            "SELECT j.id, j.recording_id, j.status, j.attempt_count, j.claim_expires_at, j.latest_error_step, j.latest_error, j.created_at, j.updated_at, j.completed_at, r.sha256, r.original_name, r.current_path, r.status AS recording_status FROM jobs j JOIN recordings r ON r.id = j.recording_id ORDER BY j.id"
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            attempts = connection.execute(
                "SELECT number, worker_host, started_at, finished_at, outcome, error_step, error_detail, cleanup_status, duration_seconds, peak_gpu_memory_mb FROM attempts WHERE job_id=? ORDER BY number",
                (row["id"],),
            ).fetchall()
            item["attempts"] = [dict(attempt) for attempt in attempts]
            results.append(item)
        return results


def claim_next(config: Config) -> Claim | None:
    now = datetime.now(UTC)
    expires = (now + timedelta(seconds=config.lease_seconds)).isoformat()
    token = secrets.token_urlsafe(24)
    with transaction(config, immediate=True) as connection:
        row = connection.execute(
            "SELECT j.*, r.sha256, r.original_name, r.size_bytes, r.status AS recording_status, r.current_path FROM jobs j JOIN recordings r ON r.id=j.recording_id WHERE j.status='pending' AND r.status='incoming' ORDER BY j.id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        attempt_number = row["attempt_count"] + 1
        changed = connection.execute(
            "UPDATE jobs SET status='processing', attempt_count=?, claim_token=?, claim_expires_at=?, latest_error_step=NULL, latest_error=NULL, updated_at=? WHERE id=? AND status='pending'",
            (attempt_number, token, expires, now.isoformat(), row["id"]),
        ).rowcount
        if changed != 1:
            return None
        attempt = connection.execute(
            "INSERT INTO attempts (job_id, number, claim_token, worker_host, started_at, cleanup_status) VALUES (?, ?, ?, ?, ?, 'not_attempted')",
            (row["id"], attempt_number, token, config.worker_host, now.isoformat()),
        )
        job = Job(row["id"], row["recording_id"], "processing", attempt_number, token, expires)
        recording = Recording(row["recording_id"], row["sha256"], row["original_name"], row["size_bytes"], row["recording_status"], Path(row["current_path"]))
        return Claim(job, recording, attempt.lastrowid, token)


def renew_claim(config: Config, job_id: int, token: str) -> bool:
    now = datetime.now(UTC)
    expires = (now + timedelta(seconds=config.lease_seconds)).isoformat()
    with transaction(config, immediate=True) as connection:
        changed = connection.execute(
            "UPDATE jobs SET claim_expires_at=?, updated_at=? WHERE id=? AND status='processing' AND claim_token=?",
            (expires, now.isoformat(), job_id, token),
        ).rowcount
    return changed == 1


def complete_claim(config: Config, claim: Claim, transcript_dir: Path, *, duration_seconds: float | None, peak_gpu_memory_mb: int | None) -> None:
    files = [p for p in transcript_dir.iterdir() if p.suffix in {".json", ".md", ".srt"} and p.stat().st_size > 0] if transcript_dir.is_dir() else []
    if {p.suffix for p in files} != {".json", ".md", ".srt"}:
        raise DomainError("required transcript outputs are missing or empty", step="completion")
    destination = config.processed_dir / claim.recording.original_name
    with connect(config) as connection:
        owned = connection.execute("SELECT 1 FROM jobs WHERE id=? AND status='processing' AND claim_token=?", (claim.job.id, claim.token)).fetchone()
    if not owned:
        raise DomainError("claim ownership was lost", step="claim_lost")
    if claim.recording.current_path.exists() and claim.recording.current_path != destination:
        os.replace(claim.recording.current_path, destination)
    now = utc_now()
    with transaction(config, immediate=True) as connection:
        changed = connection.execute(
            "UPDATE jobs SET status='complete', claim_token=NULL, claim_expires_at=NULL, completed_at=?, updated_at=? WHERE id=? AND status='processing' AND claim_token=?",
            (now, now, claim.job.id, claim.token),
        ).rowcount
        if changed != 1:
            raise DomainError("claim ownership was lost during completion", step="claim_lost")
        connection.execute("UPDATE recordings SET status='processed', current_path=?, updated_at=? WHERE id=?", (str(destination), now, claim.recording.id))
        connection.execute(
            "UPDATE attempts SET finished_at=?, outcome='complete', duration_seconds=?, peak_gpu_memory_mb=? WHERE id=? AND claim_token=?",
            (now, duration_seconds, peak_gpu_memory_mb, claim.attempt_id, claim.token),
        )


def set_cleanup_status(config: Config, attempt_id: int, status: str) -> None:
    with transaction(config) as connection:
        connection.execute("UPDATE attempts SET cleanup_status=? WHERE id=?", (status, attempt_id))


def fail_claim(config: Config, claim: Claim, step: str, detail: str) -> None:
    now = utc_now()
    detail = detail[-2000:]
    with transaction(config, immediate=True) as connection:
        changed = connection.execute(
            "UPDATE jobs SET status='failed', claim_token=NULL, claim_expires_at=NULL, latest_error_step=?, latest_error=?, updated_at=? WHERE id=? AND status='processing' AND claim_token=?",
            (step, detail, now, claim.job.id, claim.token),
        ).rowcount
        if changed:
            connection.execute(
                "UPDATE attempts SET finished_at=?, outcome='failed', error_step=?, error_detail=? WHERE id=? AND claim_token=?",
                (now, step, detail, claim.attempt_id, claim.token),
            )


def recover_expired_claims(config: Config) -> int:
    now = utc_now()
    with transaction(config, immediate=True) as connection:
        rows = connection.execute(
            "SELECT id, claim_token FROM jobs WHERE status='processing' AND claim_expires_at < ?",
            (now,),
        ).fetchall()
        for row in rows:
            detail = "controller claim expired before completion"
            connection.execute(
                "UPDATE jobs SET status='failed', claim_token=NULL, claim_expires_at=NULL, latest_error_step='claim_expired', latest_error=?, updated_at=? WHERE id=? AND status='processing' AND claim_token=?",
                (detail, now, row["id"], row["claim_token"]),
            )
            connection.execute(
                "UPDATE attempts SET finished_at=?, outcome='failed', error_step='claim_expired', error_detail=? WHERE job_id=? AND claim_token=? AND finished_at IS NULL",
                (now, detail, row["id"], row["claim_token"]),
            )
    return len(rows)


def retry_job(config: Config, job_id: int) -> None:
    now = utc_now()
    with transaction(config, immediate=True) as connection:
        row = connection.execute(
            "SELECT j.status, r.status AS recording_status FROM jobs j JOIN recordings r ON r.id=j.recording_id WHERE j.id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise DomainError("job not found", step="retry")
        if row["status"] != "failed" or row["recording_status"] != "incoming":
            raise DomainError("only a failed job with an incoming recording can be retried", step="retry")
        connection.execute(
            "UPDATE jobs SET status='pending', latest_error_step=NULL, latest_error=NULL, updated_at=? WHERE id=?",
            (now, job_id),
        )


def quarantine_job(config: Config, job_id: int, reason: str) -> Path:
    if not reason.strip():
        raise DomainError("quarantine reason is required", step="quarantine")
    with connect(config) as connection:
        row = connection.execute(
            "SELECT j.status, r.id AS recording_id, r.status AS recording_status, r.current_path, r.original_name FROM jobs j JOIN recordings r ON r.id=j.recording_id WHERE j.id=?",
            (job_id,),
        ).fetchone()
    if row is None or row["status"] != "failed" or row["recording_status"] != "incoming":
        raise DomainError("only a failed job with an incoming recording can be quarantined", step="quarantine")
    source = Path(row["current_path"])
    destination = config.failed_dir / row["original_name"]
    if destination.exists():
        raise DomainError("quarantine destination already exists", step="quarantine")
    os.replace(source, destination)
    now = utc_now()
    with transaction(config, immediate=True) as connection:
        connection.execute(
            "UPDATE recordings SET status='quarantined', current_path=?, updated_at=? WHERE id=? AND status='incoming'",
            (str(destination), now, row["recording_id"]),
        )
        connection.execute(
            "UPDATE jobs SET latest_error_step='quarantined', latest_error=?, updated_at=? WHERE id=? AND status='failed'",
            (reason.strip()[-2000:], now, job_id),
        )
    return destination
