from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

from .models import CommandResult, DomainError


MAX_DIAGNOSTIC = 2000


def scrub(text: str, secrets: Sequence[str] = ()) -> str:
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result[-MAX_DIAGNOSTIC:]


class RunningCommand:
    def __init__(self, process: subprocess.Popen[str], args: Sequence[str], secrets: Sequence[str]):
        self.process = process
        self.args = tuple(args)
        self.secrets = tuple(secrets)

    def poll(self) -> int | None:
        return self.process.poll()

    def wait(self, timeout: float | None = None) -> CommandResult:
        stdout, stderr = self.process.communicate(timeout=timeout)
        return CommandResult(self.args, self.process.returncode, scrub(stdout, self.secrets), scrub(stderr, self.secrets))

    def terminate(self) -> None:
        self.process.terminate()


class CommandRunner:
    def run(self, args: Sequence[str], *, secrets: Sequence[str] = ()) -> CommandResult:
        completed = subprocess.run(list(args), text=True, capture_output=True, check=False)
        return CommandResult(tuple(args), completed.returncode, scrub(completed.stdout, secrets), scrub(completed.stderr, secrets))

    def start(self, args: Sequence[str], *, secrets: Sequence[str] = ()) -> RunningCommand:
        process = subprocess.Popen(list(args), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return RunningCommand(process, args, secrets)


def require_success(result: CommandResult, step: str) -> None:
    if not result.ok:
        detail = result.stderr or result.stdout or f"exit status {result.returncode}"
        raise DomainError(detail, step=step)
