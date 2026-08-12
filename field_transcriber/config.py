"""Configuration with no third-party dependency."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


PREFIX = "FIELD_TRANSCRIBER_"
KNOWN_KEYS = {
    "ROOT",
    "WORKER_HOST",
    "WORKER_USER",
    "WORKER_IMAGE",
    "REMOTE_ROOT",
    "CLAIM_LEASE_SECONDS",
    "HEARTBEAT_SECONDS",
    "HF_TOKEN_ENV",
    "PYTHON",
    "WORKER_MODE",
    "RUNPOD_ENDPOINT_ID",
    "RUNPOD_API_KEY_ENV",
    "REMOTE_EXECUTION_TIMEOUT_MS",
    "REMOTE_TTL_MS",
    "REMOTE_POLL_SECONDS",
    "REMOTE_RESOLUTION_SECONDS",
    "TRANSFER_RETENTION_SECONDS",
    "OBJECT_STORE_ENDPOINT",
    "OBJECT_STORE_BUCKET",
    "OBJECT_STORE_REGION",
    "OBJECT_STORE_ACCESS_KEY_ENV",
    "OBJECT_STORE_SECRET_KEY_ENV",
    "OBJECT_URL_TTL_SECONDS",
}


@dataclass(frozen=True)
class Config:
    root: Path
    worker_host: str = ""
    worker_user: str = "assela"
    worker_image: str = "field-transcriber-worker:local"
    remote_root: str = "/home/assela/field-transcriber-jobs"
    lease_seconds: int = 300
    heartbeat_seconds: int = 60
    hf_token_env: str = "HF_TOKEN"
    python_command: str = "python3"
    worker_mode: str = "ssh"
    runpod_endpoint_id: str = ""
    runpod_api_key_env: str = "RUNPOD_API_KEY"
    remote_execution_timeout_ms: int = 7_200_000
    remote_ttl_ms: int = 10_800_000
    remote_poll_seconds: int = 10
    remote_resolution_seconds: int = 1800
    transfer_retention_seconds: int = 86400
    object_store_endpoint: str = ""
    object_store_bucket: str = ""
    object_store_region: str = "us-east-1"
    object_store_access_key_env: str = "S3_ACCESS_KEY_ID"
    object_store_secret_key_env: str = "S3_SECRET_ACCESS_KEY"
    object_url_ttl_seconds: int = 10800

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser())
        if not self.root.is_absolute():
            raise ConfigError("FIELD_TRANSCRIBER_ROOT must be an absolute path")
        if self.lease_seconds <= 0 or self.heartbeat_seconds <= 0:
            raise ConfigError("lease and heartbeat values must be positive")
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ConfigError("heartbeat must be shorter than the claim lease")
        if self.worker_mode not in {"ssh", "runpod"}:
            raise ConfigError("worker mode must be ssh or runpod")
        positive = (
            self.remote_execution_timeout_ms,
            self.remote_ttl_ms,
            self.remote_poll_seconds,
            self.remote_resolution_seconds,
            self.transfer_retention_seconds,
            self.object_url_ttl_seconds,
        )
        if any(value <= 0 for value in positive):
            raise ConfigError("remote timing values must be positive")
        if self.remote_ttl_ms <= self.remote_execution_timeout_ms:
            raise ConfigError("remote TTL must be greater than execution timeout")
        if self.worker_mode == "runpod":
            required = (self.runpod_endpoint_id, self.object_store_endpoint, self.object_store_bucket)
            if not all(required):
                raise ConfigError("runpod mode requires endpoint ID and object-store settings")
            if not self.object_store_endpoint.startswith("https://") and not self.object_store_endpoint.startswith("http://localhost"):
                raise ConfigError("object-store endpoint must use HTTPS")

    @property
    def uploading_dir(self) -> Path:
        return self.root / "uploading"

    @property
    def incoming_dir(self) -> Path:
        return self.root / "incoming"

    @property
    def processed_dir(self) -> Path:
        return self.root / "processed"

    @property
    def failed_dir(self) -> Path:
        return self.root / "failed"

    @property
    def transcripts_dir(self) -> Path:
        return self.root / "transcripts"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def db_path(self) -> Path:
        return self.state_dir / "jobs.db"


def _parse_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ConfigError(f"configuration file not found: {path}")
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"invalid configuration line {number}")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key.startswith(PREFIX) or key.removeprefix(PREFIX) not in KNOWN_KEYS:
            raise ConfigError(f"unknown configuration key: {key}")
        values[key] = value
    return values


def load_config(path: Path | str | None = None) -> Config:
    values: dict[str, str] = {}
    if path is not None:
        values.update(_parse_file(Path(path)))
    for key in KNOWN_KEYS:
        full = PREFIX + key
        if full in os.environ:
            values[full] = os.environ[full]
    root = values.get(PREFIX + "ROOT")
    if not root:
        raise ConfigError("configuration must define FIELD_TRANSCRIBER_ROOT")
    try:
        return Config(
            root=Path(root),
            worker_host=values.get(PREFIX + "WORKER_HOST", ""),
            worker_user=values.get(PREFIX + "WORKER_USER", "assela"),
            worker_image=values.get(PREFIX + "WORKER_IMAGE", "field-transcriber-worker:local"),
            remote_root=values.get(PREFIX + "REMOTE_ROOT", "/home/assela/field-transcriber-jobs"),
            lease_seconds=int(values.get(PREFIX + "CLAIM_LEASE_SECONDS", "300")),
            heartbeat_seconds=int(values.get(PREFIX + "HEARTBEAT_SECONDS", "60")),
            hf_token_env=values.get(PREFIX + "HF_TOKEN_ENV", "HF_TOKEN"),
            python_command=values.get(PREFIX + "PYTHON", "python3"),
            worker_mode=values.get(PREFIX + "WORKER_MODE", "ssh"),
            runpod_endpoint_id=values.get(PREFIX + "RUNPOD_ENDPOINT_ID", ""),
            runpod_api_key_env=values.get(PREFIX + "RUNPOD_API_KEY_ENV", "RUNPOD_API_KEY"),
            remote_execution_timeout_ms=int(values.get(PREFIX + "REMOTE_EXECUTION_TIMEOUT_MS", "7200000")),
            remote_ttl_ms=int(values.get(PREFIX + "REMOTE_TTL_MS", "10800000")),
            remote_poll_seconds=int(values.get(PREFIX + "REMOTE_POLL_SECONDS", "10")),
            remote_resolution_seconds=int(values.get(PREFIX + "REMOTE_RESOLUTION_SECONDS", "1800")),
            transfer_retention_seconds=int(values.get(PREFIX + "TRANSFER_RETENTION_SECONDS", "86400")),
            object_store_endpoint=values.get(PREFIX + "OBJECT_STORE_ENDPOINT", ""),
            object_store_bucket=values.get(PREFIX + "OBJECT_STORE_BUCKET", ""),
            object_store_region=values.get(PREFIX + "OBJECT_STORE_REGION", "us-east-1"),
            object_store_access_key_env=values.get(PREFIX + "OBJECT_STORE_ACCESS_KEY_ENV", "S3_ACCESS_KEY_ID"),
            object_store_secret_key_env=values.get(PREFIX + "OBJECT_STORE_SECRET_KEY_ENV", "S3_SECRET_ACCESS_KEY"),
            object_url_ttl_seconds=int(values.get(PREFIX + "OBJECT_URL_TTL_SECONDS", "10800")),
        )
    except ValueError as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"invalid numeric configuration: {exc}") from exc
