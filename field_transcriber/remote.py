"""Provider-neutral remote execution and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import secrets
import time
from pathlib import Path
from typing import Protocol

from .commands import scrub
from .config import Config
from .db import connect, transaction
from .jobs import claim_next, complete_claim, fail_claim, reclaim_remote_claim, utc_now
from .models import Claim, DomainError, Job, Recording
from .object_store import ObjectNotFound, ObjectStore
from .orchestrator import publish_result

REMOTE_STATES = frozenset({"queued", "running", "succeeded", "failed", "cancelled", "expired", "indeterminate"})


@dataclass(frozen=True)
class RemoteRequest:
    idempotency_key: str
    recording_sha256: str
    original_name: str
    input_url: str
    result_url: str
    execution_timeout_ms: int
    ttl_ms: int


@dataclass(frozen=True)
class RemoteStatus:
    state: str
    external_job_id: str | None = None
    diagnostic: str | None = None
    result_manifest: dict | None = None

    def __post_init__(self) -> None:
        if self.state not in REMOTE_STATES:
            raise ValueError(f"unknown remote state: {self.state}")


class Provider(Protocol):
    def submit(self, request: RemoteRequest) -> RemoteStatus: ...
    def status(self, external_job_id: str) -> RemoteStatus: ...
    def cancel(self, external_job_id: str) -> RemoteStatus: ...


def bounded_diagnostic(value: object, secrets: tuple[str, ...] = ()) -> str:
    return scrub(str(value), secrets)[-2000:]


def reconcile_time(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def _claim_from_row(row) -> Claim:
    job = Job(row["job_id"], row["recording_id"], "processing", row["attempt_count"], row["claim_token"], row["claim_expires_at"])
    recording = Recording(row["recording_id"], row["sha256"], row["original_name"], row["size_bytes"], row["recording_status"], Path(row["current_path"]))
    return Claim(job, recording, row["attempt_id"], row["claim_token"])


def _execution_rows(config: Config, job_id: int | None = None):
    where = " AND j.id=?" if job_id is not None else ""
    parameters = (job_id,) if job_id is not None else ()
    with connect(config) as connection:
        return connection.execute(
            "SELECT re.*, a.job_id, a.id AS attempt_id, j.recording_id, j.attempt_count, j.claim_token, j.claim_expires_at, "
            "r.sha256, r.original_name, r.size_bytes, r.status AS recording_status, r.current_path "
            "FROM remote_executions re JOIN attempts a ON a.id=re.attempt_id JOIN jobs j ON j.id=a.job_id "
            "JOIN recordings r ON r.id=j.recording_id WHERE j.status='processing' AND re.state!='abandoned' "
            "AND a.finished_at IS NULL AND a.claim_token=j.claim_token" + where,
            parameters,
        ).fetchall()


def _set_remote(config: Config, execution_id: int, status: RemoteStatus) -> None:
    with transaction(config, immediate=True) as connection:
        connection.execute(
            "UPDATE remote_executions SET external_job_id=COALESCE(external_job_id,?), state=?, diagnostic=?, last_reconciled_at=?, reconcile_after=? WHERE id=?",
            (status.external_job_id, status.state, status.diagnostic, utc_now(), reconcile_time(config.remote_poll_seconds), execution_id),
        )


def _retain_transfers(config: Config, execution_id: int) -> None:
    retain_until = (datetime.now(UTC) + timedelta(seconds=config.transfer_retention_seconds)).isoformat()
    with transaction(config) as connection:
        connection.execute(
            "UPDATE transfer_objects SET retain_until=?, updated_at=? WHERE remote_execution_id=? AND state!='deleted'",
            (retain_until, utc_now(), execution_id),
        )


def _publish_result(config: Config, store: ObjectStore, row, claim: Claim) -> tuple[dict | None, str | None]:
    result_key = row["result_reference"]
    try:
        if not result_key or not store.exists(result_key):
            return None, None
        body = store.download(result_key)
        document = json.loads(body)
        transcript_dir = publish_result(config, claim, document)
        run = document.get("run", {})
        complete_claim(config, claim, transcript_dir, duration_seconds=run.get("duration_seconds"), peak_gpu_memory_mb=run.get("peak_gpu_memory_mb"))
    except ObjectNotFound:
        return None, None
    except (OSError, ValueError, json.JSONDecodeError, DomainError) as exc:
        return None, bounded_diagnostic(exc)
    cleanup = "complete"
    with connect(config) as connection:
        objects = connection.execute("SELECT id, object_key FROM transfer_objects WHERE remote_execution_id=?", (row["id"],)).fetchall()
    for item in objects:
        try:
            store.delete(item["object_key"])
            state = "deleted"
        except OSError:
            state, cleanup = "cleanup_failed", "failed"
        with transaction(config) as connection:
            connection.execute("UPDATE transfer_objects SET state=?, updated_at=? WHERE id=?", (state, utc_now(), item["id"]))
    _set_remote(config, row["id"], RemoteStatus("succeeded", row["external_job_id"]))
    return {"result": "complete", "job_id": claim.job.id, "provider": row["provider"], "external_job_id": row["external_job_id"], "remote_state": "succeeded", "cleanup": cleanup}, None


def reconcile(config: Config, provider: Provider, store: ObjectStore, *, job_id: int | None = None) -> list[dict]:
    outcomes = []
    for row in _execution_rows(config, job_id):
        claim = _claim_from_row(row)
        completed, probe_error = _publish_result(config, store, row, claim)
        if completed:
            outcomes.append(completed)
            continue
        if row["external_job_id"]:
            status = provider.status(row["external_job_id"])
        else:
            status = RemoteStatus("indeterminate", diagnostic=row["diagnostic"])
        if probe_error:
            status = RemoteStatus(status.state, status.external_job_id, probe_error, status.result_manifest)
        _set_remote(config, row["id"], status)
        if status.state in {"queued", "running"}:
            claim = reclaim_remote_claim(config, row["job_id"], row["attempt_id"])
            outcomes.append({"result": "remote_active", "job_id": claim.job.id, "provider": row["provider"], "external_job_id": status.external_job_id, "remote_state": status.state})
        elif status.state in {"failed", "cancelled", "expired"}:
            _retain_transfers(config, row["id"])
            fail_claim(config, claim, f"remote_{status.state}", status.diagnostic or f"remote job {status.state}")
            outcomes.append({"result": "failed", "job_id": claim.job.id, "remote_state": status.state})
        elif status.state == "succeeded":
            if probe_error:
                _set_remote(config, row["id"], RemoteStatus("indeterminate", row["external_job_id"], probe_error))
                outcomes.append({"result": "indeterminate", "job_id": claim.job.id, "remote_state": "indeterminate"})
            else:
                # Object stores can briefly lag the provider's terminal status. Keep
                # the same attempt alive and let result-first reconciliation retry.
                claim = reclaim_remote_claim(config, row["job_id"], row["attempt_id"])
                outcomes.append({"result": "remote_active", "job_id": claim.job.id, "provider": row["provider"], "external_job_id": status.external_job_id, "remote_state": "succeeded"})
        else:
            outcomes.append({"result": "indeterminate", "job_id": claim.job.id, "remote_state": "indeterminate"})
    return outcomes


def _wait(config: Config, provider: Provider, store: ObjectStore, outcome: dict, sleep) -> dict:
    while sleep is not None and outcome.get("result") == "remote_active":
        sleep(config.remote_poll_seconds)
        outcome = reconcile(config, provider, store, job_id=outcome["job_id"])[0]
    return outcome


def submit_next(config: Config, provider: Provider, store: ObjectStore, *, sleep=time.sleep) -> dict:
    active = reconcile(config, provider, store)
    if active:
        return _wait(config, provider, store, active[0], sleep)
    claim = claim_next(config)
    if claim is None:
        return {"result": "no_job"}
    now = utc_now()
    idempotency_key = secrets.token_urlsafe(32)
    prefix = f"attempts/{claim.attempt_id}/{claim.recording.sha256}"
    input_key, result_key = f"{prefix}/recording.mp3", f"{prefix}/transcript.json"
    with transaction(config, immediate=True) as connection:
        cursor = connection.execute(
            "INSERT INTO remote_executions (attempt_id,provider,idempotency_key,state,submitted_at,reconcile_after,execution_timeout_ms,ttl_ms,result_reference) VALUES (?,'runpod',?,'submitting',?,?,?,?,?)",
            (claim.attempt_id, idempotency_key, now, reconcile_time(config.remote_poll_seconds), config.remote_execution_timeout_ms, config.remote_ttl_ms, result_key),
        )
        execution_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO transfer_objects (remote_execution_id,direction,object_key,sha256,size_bytes,state,updated_at) VALUES (?,?,?,?,?,'pending',?)",
            ((execution_id, "input", input_key, claim.recording.sha256, claim.recording.size_bytes, now), (execution_id, "result", result_key, None, None, now)),
        )
    try:
        store.upload(input_key, claim.recording.current_path)
        with transaction(config) as connection:
            connection.execute("UPDATE transfer_objects SET state='uploaded', updated_at=? WHERE remote_execution_id=? AND direction='input'", (utc_now(), execution_id))
    except Exception as exc:
        _retain_transfers(config, execution_id)
        fail_claim(config, claim, "transfer_upload", bounded_diagnostic(exc))
        return {"result": "failed", "job_id": claim.job.id, "provider": "runpod", "remote_state": "failed"}
    request = RemoteRequest(idempotency_key, claim.recording.sha256, claim.recording.original_name, store.presign("GET", input_key, config.object_url_ttl_seconds), store.presign("PUT", result_key, config.object_url_ttl_seconds), config.remote_execution_timeout_ms, config.remote_ttl_ms)
    try:
        status = provider.submit(request)
        _set_remote(config, execution_id, status)
        if status.state == "indeterminate":
            return {"result": "indeterminate", "job_id": claim.job.id, "provider": "runpod", "remote_state": status.state}
        outcome = {"result": "remote_active" if status.state in {"queued", "running"} else "submitted", "job_id": claim.job.id, "provider": "runpod", "external_job_id": status.external_job_id, "remote_state": status.state}
        return _wait(config, provider, store, outcome, sleep)
    except Exception as exc:
        status = RemoteStatus("indeterminate", diagnostic=bounded_diagnostic(exc))
        _set_remote(config, execution_id, status)
        return {"result": "indeterminate", "job_id": claim.job.id, "provider": "runpod", "remote_state": "indeterminate"}


def cleanup_transfers(config: Config, store: ObjectStore) -> list[dict]:
    now = utc_now()
    with connect(config) as connection:
        rows = connection.execute(
            "SELECT id, object_key FROM transfer_objects WHERE state='cleanup_failed' "
            "OR (state!='deleted' AND retain_until IS NOT NULL AND retain_until<=?)",
            (now,),
        ).fetchall()
    outcomes = []
    for row in rows:
        try:
            store.delete(row["object_key"])
            state = "deleted"
        except OSError:
            state = "cleanup_failed"
        with transaction(config) as connection:
            connection.execute("UPDATE transfer_objects SET state=?, updated_at=? WHERE id=?", (state, utc_now(), row["id"]))
        outcomes.append({"object_key": row["object_key"], "state": state})
    return outcomes


def cancel_remote(config: Config, provider: Provider, store: ObjectStore, job_id: int) -> dict:
    outcomes = reconcile(config, provider, store, job_id=job_id)
    if outcomes and outcomes[0].get("result") == "complete":
        return outcomes[0]
    rows = _execution_rows(config, job_id)
    if not rows or not rows[0]["external_job_id"]:
        raise DomainError("active remote job not found", step="cancel")
    provider.cancel(rows[0]["external_job_id"])
    return reconcile(config, provider, store, job_id=job_id)[0]


def resolve_remote(config: Config, job_id: int, decision: str) -> dict:
    if decision not in {"wait", "abandon-retry"}:
        raise DomainError("invalid remote resolution decision", step="resolve_remote")
    rows = _execution_rows(config, job_id)
    if not rows or rows[0]["state"] != "indeterminate" or rows[0]["reconcile_after"] > utc_now():
        raise DomainError("remote execution is not eligible for owner resolution", step="resolve_remote")
    row = rows[0]
    with transaction(config, immediate=True) as connection:
        if decision == "wait":
            connection.execute("UPDATE remote_executions SET owner_resolution='wait', resolved_at=?, reconcile_after=? WHERE id=?", (utc_now(), reconcile_time(config.remote_resolution_seconds), row["id"]))
        else:
            connection.execute("UPDATE remote_executions SET state='abandoned', owner_resolution='abandon_retry', resolved_at=? WHERE id=?", (utc_now(), row["id"]))
    if decision == "abandon-retry":
        _retain_transfers(config, row["id"])
        fail_claim(config, _claim_from_row(row), "remote_abandoned", "owner authorized abandon and retry")
    return {"result": decision.replace("-", "_"), "job_id": job_id}
