"""VPS-controlled disposable-worker orchestration."""

from __future__ import annotations

import json
import os
import shlex
import tempfile
import time
from pathlib import Path
from typing import Callable

from .commands import CommandRunner, require_success, scrub
from .config import Config
from .jobs import assert_claim_owned, claim_next, complete_claim, fail_claim, reconcile_interrupted_completions, recover_expired_claims, renew_claim, set_cleanup_status
from .models import Claim, DomainError
from .renderers import publish_transcripts
from .transcript import validate_transcript


def _remote_dependencies(config: Config):
    from .object_store import ObjectStore
    from .runpod_provider import RunpodProvider

    api_key = os.environ.get(config.runpod_api_key_env, "")
    access_key = os.environ.get(config.object_store_access_key_env, "")
    secret_key = os.environ.get(config.object_store_secret_key_env, "")
    if not api_key or not access_key or not secret_key:
        raise DomainError("runpod and object-store runtime credentials are required", step="configuration")
    return (
        RunpodProvider(config.runpod_endpoint_id, api_key),
        ObjectStore(config.object_store_endpoint, config.object_store_bucket, config.object_store_region, access_key, secret_key),
    )


def _target(config: Config) -> str:
    if not config.worker_host:
        raise DomainError("worker host is not configured", step="configuration")
    return f"{config.worker_user}@{config.worker_host}"


def _remote_dir(config: Config, claim: Claim) -> str:
    return f"{config.remote_root.rstrip('/')}/{claim.recording.sha256}-{claim.job.attempt_count}"


def _cleanup(config: Config, claim: Claim, runner: CommandRunner) -> bool:
    remote = _remote_dir(config, claim)
    result = runner.run(["ssh", _target(config), f"rm -rf -- {shlex.quote(remote)}"])
    set_cleanup_status(config, claim.attempt_id, "complete" if result.ok else "failed")
    return result.ok


def publish_result(config: Config, claim: Claim, document: dict) -> Path:
    validate_transcript(document, claim.recording.sha256)
    assert_claim_owned(config, claim)
    return publish_transcripts(document, config.transcripts_dir, claim.recording.sha256)[0].parent


def run_next(config: Config, *, runner: CommandRunner | None = None, sleep: Callable[[float], None] = time.sleep, provider=None, store=None) -> dict:
    if config.worker_mode == "runpod":
        from .remote import cleanup_transfers, submit_next

        if provider is None or store is None:
            provider, store = _remote_dependencies(config)
        cleanup_transfers(config, store)
        recover_expired_claims(config)
        return submit_next(config, provider, store, sleep=sleep)
    runner = runner or CommandRunner()
    reconcile_interrupted_completions(config)
    recover_expired_claims(config)
    claim = claim_next(config)
    if claim is None:
        return {"result": "no_job"}
    remote = _remote_dir(config, claim)
    target = _target(config)
    token = os.environ.get(config.hf_token_env, "")
    if not token:
        fail_claim(config, claim, "configuration", f"{config.hf_token_env} is not set")
        raise DomainError(f"{config.hf_token_env} is not set", step="configuration")
    try:
        require_success(runner.run(["ssh", target, f"mkdir -p -- {shlex.quote(remote + '/output')}"]), "worker_prepare")
        require_success(runner.run(["scp", str(claim.recording.current_path), f"{target}:{remote}/recording.mp3"]), "worker_upload")
        docker = (
            f"docker run --rm --gpus all -e HF_TOKEN={shlex.quote(token)} "
            f"-v {shlex.quote(remote + '/recording.mp3')}:/input/recording.mp3:ro "
            f"-v {shlex.quote(remote + '/output')}:/output "
            f"{shlex.quote(config.worker_image)} --input /input/recording.mp3 "
            f"--output /output/transcript.json --recording-sha256 {claim.recording.sha256} "
            f"--original-name {shlex.quote(claim.recording.original_name)}"
        )
        running = runner.start(["ssh", target, docker], secrets=(token,))
        while running.poll() is None:
            sleep(config.heartbeat_seconds)
            if not renew_claim(config, claim.job.id, claim.token):
                running.terminate()
                _cleanup(config, claim, runner)
                raise DomainError("claim ownership was lost during worker execution", step="claim_lost")
        require_success(running.wait(), "worker_run")
        if not renew_claim(config, claim.job.id, claim.token):
            raise DomainError("claim ownership was lost before result pull", step="claim_lost")
        with tempfile.TemporaryDirectory(prefix="field-transcriber-result-", dir=config.state_dir) as directory:
            staged = Path(directory) / "transcript.json"
            require_success(runner.run(["scp", f"{target}:{remote}/output/transcript.json", str(staged)]), "result_pull")
            try:
                document = json.loads(staged.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DomainError(f"invalid result JSON: {exc}", step="result_validation") from exc
            transcript_dir = publish_result(config, claim, document)
            run = document.get("run", {})
            complete_claim(
                config,
                claim,
                transcript_dir,
                duration_seconds=run.get("duration_seconds"),
                peak_gpu_memory_mb=run.get("peak_gpu_memory_mb"),
            )
        cleanup_ok = _cleanup(config, claim, runner)
        return {"result": "complete", "job_id": claim.job.id, "sha256": claim.recording.sha256, "cleanup": "complete" if cleanup_ok else "failed"}
    except DomainError as exc:
        fail_claim(config, claim, exc.step, scrub(str(exc), (token,)))
        raise
    except Exception as exc:
        detail = scrub(f"{type(exc).__name__}: {exc}", (token,))
        fail_claim(config, claim, "controller_unexpected", detail)
        raise DomainError(detail, step="controller_unexpected") from exc
