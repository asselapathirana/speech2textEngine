"""Immutable source recording publication and discovery."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .config import Config
from .jobs import find_recording_by_digest, register_recording
from .models import DomainError, Recording


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*\.mp3$", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_name(name: str) -> str:
    if Path(name).name != name or not SAFE_NAME.fullmatch(name):
        raise DomainError("recording name must be a safe MP3 basename", step="input")
    return name


def publish_upload(config: Config, staged_name: str, original_name: str, size: int, digest: str) -> Recording:
    validate_name(original_name)
    if Path(staged_name).name != staged_name:
        raise DomainError("invalid staged filename", step="upload_verify")
    staged = config.uploading_dir / staged_name
    if not staged.is_file():
        raise DomainError("staged upload does not exist", step="upload_verify")
    actual_size = staged.stat().st_size
    if actual_size != size or size <= 0:
        raise DomainError(f"staged upload is incomplete: expected {size} bytes, found {actual_size}", step="upload_verify")
    actual_digest = sha256_file(staged)
    if actual_digest != digest or len(digest) != 64:
        raise DomainError("staged upload digest does not match source", step="upload_verify")
    existing = find_recording_by_digest(config, digest)
    if existing:
        staged.unlink()
        return existing
    target = config.incoming_dir / original_name
    if target.exists():
        if sha256_file(target) != digest:
            raise DomainError(f"filename collision: {original_name}", step="upload_publish")
        staged.unlink()
    else:
        os.replace(staged, target)
    return register_recording(config, digest, original_name, size, target)


def discover(config: Config) -> list[Recording]:
    found: list[Recording] = []
    for path in sorted(config.incoming_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".mp3" or path.stat().st_size <= 0:
            continue
        digest = sha256_file(path)
        found.append(register_recording(config, digest, path.name, path.stat().st_size, path))
    return found
