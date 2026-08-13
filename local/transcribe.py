#!/home/assela/python/.venv/bin/python
"""Transcribe MP3 paths or wildcard patterns and save results beside each file."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ACTIVE = {"pending", "processing"}
FINAL = {"complete", "failed", "quarantined"}
REQUIRED_OUTPUTS = ("transcript.json", "transcript.md", "transcript.srt")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected NAME=value")
        name, value = line.split("=", 1)
        values[name.strip()] = value.strip().strip("'\"")
    return values


def select_job(jobs: list[dict], digest: str) -> dict:
    matches = [job for job in jobs if job.get("sha256") == digest]
    if len(matches) != 1:
        raise RuntimeError(f"expected one VPS job for {digest}, found {len(matches)}")
    target = matches[0]
    if target.get("status") != "complete":
        blockers = [job for job in jobs if job.get("sha256") != digest and job.get("status") in ACTIVE]
        if blockers:
            details = ", ".join(f"job {job['id']} ({job['status']})" for job in blockers)
            raise RuntimeError(f"another queued job would run first: {details}")
    return target


class Vps:
    def __init__(self, values: dict[str, str]):
        required = ("FIELD_TRANSCRIBER_VPS_HOST", "FIELD_TRANSCRIBER_VPS_USER", "FIELD_TRANSCRIBER_VPS_CODE", "FIELD_TRANSCRIBER_VPS_FILES")
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise ValueError(f"missing configuration: {', '.join(missing)}")
        self.remote = f"{values['FIELD_TRANSCRIBER_VPS_USER']}@{values['FIELD_TRANSCRIBER_VPS_HOST']}"
        self.code = values["FIELD_TRANSCRIBER_VPS_CODE"]
        self.files = values["FIELD_TRANSCRIBER_VPS_FILES"]
        self.python = values.get("FIELD_TRANSCRIBER_VPS_PYTHON", "python3")
        self.runtime_config = values.get("FIELD_TRANSCRIBER_VPS_RUNTIME_CONFIG", "/home/assela/field-transcriber/runtime/config.env")
        self.secrets = values.get("FIELD_TRANSCRIBER_VPS_SECRETS", "/home/assela/field-transcriber/runtime/secrets.env")

    def cli(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = (
            f"set -a; . {shlex.quote(self.secrets)}; set +a; "
            f"cd {shlex.quote(self.code)}; {shlex.quote(self.python)} -m field_transcriber "
            f"--config {shlex.quote(self.runtime_config)} "
            + " ".join(shlex.quote(argument) for argument in arguments)
        )
        return subprocess.run(["ssh", self.remote, command], text=True, capture_output=True, check=check)

    def json(self, *arguments: str) -> dict:
        result = self.cli(*arguments, "--json")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"VPS returned invalid JSON: {result.stdout.strip() or result.stderr.strip()}") from exc


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"recording not found: {path}")
    if path.suffix.lower() != ".mp3":
        raise ValueError("recording must have an MP3 extension")


def remote_name(path: Path, digest: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._-") or "recording"
    return f"{stem}-{digest[:12]}.mp3"


def resolve_sources(patterns: list[str]) -> list[Path]:
    sources: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        expanded = os.path.expanduser(pattern)
        matches = sorted(Path(match).resolve() for match in glob.glob(expanded, recursive=True) if Path(match).is_file())
        if not matches:
            raise ValueError(f"no files matched: {pattern}")
        for match in matches:
            if match not in seen:
                validate_source(match)
                seen.add(match)
                sources.append(match)
    return sources


def status_line(job: dict) -> str:
    remote = job.get("remote_execution") or {}
    detail = f", Runpod {remote['state']}" if remote.get("state") else ""
    return f"job {job['id']}: {job['status']}{detail}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", help="MP3 paths or quoted wildcard patterns")
    parser.add_argument("--poll-seconds", type=float, default=10)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.env"))
    return parser.parse_args()


def process_one(source: Path, vps: Vps, poll_seconds: float) -> None:
    digest = file_digest(source)
    uploaded_name = remote_name(source, digest)
    staged = f"{uploaded_name}.partial"
    print(f"Uploading {source.name} ({digest[:12]})")
    subprocess.run(
        ["rsync", "--partial", "--append-verify", "--", str(source), f"{vps.remote}:{vps.files}/uploading/{staged}"],
        check=True,
    )
    vps.json(
        "publish-upload", "--staged-name", staged, "--original-name", uploaded_name,
        "--size", str(source.stat().st_size), "--sha256", digest,
    )

    job = select_job(vps.json("status")["jobs"], digest)
    if job["status"] == "failed":
        print(f"Retrying failed job {job['id']}")
        vps.json("retry", "--job", str(job["id"]))
        job = vps.json("status", "--job", str(job["id"]))["jobs"][0]

    controller: subprocess.Popen[str] | None = None
    if job["status"] != "complete":
        if job["status"] not in ACTIVE:
            raise RuntimeError(f"job {job['id']} cannot be started from state {job['status']}")
        action = "Submitting" if job["status"] == "pending" else "Resuming monitoring of"
        print(f"{action} job {job['id']}")
        command = (
            f"set -a; . {shlex.quote(vps.secrets)}; set +a; cd {shlex.quote(vps.code)}; "
            f"{shlex.quote(vps.python)} -m field_transcriber --config {shlex.quote(vps.runtime_config)} run-next --json"
        )
        controller = subprocess.Popen(["ssh", vps.remote, command], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        previous = ""
        while True:
            job = vps.json("status", "--job", str(job["id"]))["jobs"][0]
            current = status_line(job)
            if current != previous:
                print(current)
                previous = current
            if job["status"] in FINAL:
                break
            if controller.poll() is not None:
                stdout, stderr = controller.communicate()
                raise RuntimeError(f"VPS controller stopped before completion: {(stderr or stdout).strip()}")
            time.sleep(poll_seconds)

        stdout, stderr = controller.communicate()
        if controller.returncode != 0:
            raise RuntimeError(f"VPS controller failed: {(stderr or stdout).strip()}")

    if job["status"] != "complete":
        error = job.get("latest_error") or "no diagnostic supplied"
        raise RuntimeError(f"job {job['id']} ended as {job['status']}: {error}")

    print(f"Downloading results beside {source}")
    with tempfile.TemporaryDirectory(prefix=".transcript-download-", dir=source.parent) as temporary:
        download = Path(temporary)
        subprocess.run(["rsync", "-a", "--", f"{vps.remote}:{vps.files}/transcripts/{digest}/", f"{download}/"], check=True)
        missing = [name for name in REQUIRED_OUTPUTS if not (download / name).is_file() or not (download / name).stat().st_size]
        if missing:
            raise RuntimeError(f"download incomplete, missing: {', '.join(missing)}")
        for name in REQUIRED_OUTPUTS:
            suffix = Path(name).suffix
            (download / name).replace(source.with_name(f"{source.stem}.transcript{suffix}"))
    print(f"Complete: {source.with_name(source.stem + '.transcript.md')}")


def main() -> int:
    args = parse_args()
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be positive")
    if not args.config.is_file():
        raise ValueError(f"configuration not found: {args.config}; copy local/config.example.env to local/config.env")
    sources = resolve_sources(args.recordings)
    vps = Vps(load_env(args.config))
    failures: list[tuple[Path, Exception]] = []
    for number, source in enumerate(sources, 1):
        if len(sources) > 1:
            print(f"\n[{number}/{len(sources)}] {source}")
        try:
            process_one(source, vps, args.poll_seconds)
        except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            failures.append((source, exc))
            print(f"error: {source}: {exc}", file=sys.stderr)
    if failures:
        raise RuntimeError(f"{len(failures)} of {len(sources)} recording(s) failed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
