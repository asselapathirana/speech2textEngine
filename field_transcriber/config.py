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

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser())
        if not self.root.is_absolute():
            raise ConfigError("FIELD_TRANSCRIBER_ROOT must be an absolute path")
        if self.lease_seconds <= 0 or self.heartbeat_seconds <= 0:
            raise ConfigError("lease and heartbeat values must be positive")
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ConfigError("heartbeat must be shorter than the claim lease")

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
        )
    except ValueError as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"invalid numeric configuration: {exc}") from exc
