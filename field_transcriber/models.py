from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DomainError(RuntimeError):
    def __init__(self, message: str, *, step: str = "controller"):
        super().__init__(message)
        self.step = step


@dataclass(frozen=True)
class Recording:
    id: int
    sha256: str
    original_name: str
    size_bytes: int
    status: str
    current_path: Path


@dataclass(frozen=True)
class Job:
    id: int
    recording_id: int
    status: str
    attempt_count: int
    claim_token: str | None = None
    claim_expires_at: str | None = None


@dataclass(frozen=True)
class Claim:
    job: Job
    recording: Recording
    attempt_id: int
    token: str


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


JsonObject = dict[str, Any]
