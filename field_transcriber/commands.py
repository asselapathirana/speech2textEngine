from __future__ import annotations

import subprocess
import tempfile
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
    def __init__(self, process: subprocess.Popen[bytes], args: Sequence[str], secrets: Sequence[str], stdout, stderr):
        self.process = process
        self.args = tuple(args)
        self.secrets = tuple(secrets)
        self.stdout = stdout
        self.stderr = stderr

    def poll(self) -> int | None:
        return self.process.poll()

    def wait(self, timeout: float | None = None) -> CommandResult:
        self.process.wait(timeout=timeout)
        stdout = self._read_tail(self.stdout)
        stderr = self._read_tail(self.stderr)
        self.stdout.close()
        self.stderr.close()
        return CommandResult(self.args, self.process.returncode, scrub(stdout, self.secrets), scrub(stderr, self.secrets))

    @staticmethod
    def _read_tail(stream) -> str:
        stream.flush()
        size = stream.seek(0, 2)
        stream.seek(max(0, size - (MAX_DIAGNOSTIC * 4)))
        return stream.read().decode("utf-8", errors="replace")

    def terminate(self) -> None:
        self.process.terminate()


class CommandRunner:
    def run(self, args: Sequence[str], *, secrets: Sequence[str] = ()) -> CommandResult:
        completed = subprocess.run(list(args), text=True, capture_output=True, check=False)
        return CommandResult(tuple(args), completed.returncode, scrub(completed.stdout, secrets), scrub(completed.stderr, secrets))

    def start(self, args: Sequence[str], *, secrets: Sequence[str] = ()) -> RunningCommand:
        stdout = tempfile.TemporaryFile(mode="w+b")
        stderr = tempfile.TemporaryFile(mode="w+b")
        try:
            process = subprocess.Popen(list(args), stdout=stdout, stderr=stderr)
        except Exception:
            stdout.close()
            stderr.close()
            raise
        return RunningCommand(process, args, secrets, stdout, stderr)


def require_success(result: CommandResult, step: str) -> None:
    if not result.ok:
        detail = result.stderr or result.stdout or f"exit status {result.returncode}"
        raise DomainError(detail, step=step)
