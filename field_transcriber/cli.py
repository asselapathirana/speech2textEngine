from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .config import ConfigError, load_config
from .db import initialize
from .jobs import list_jobs, quarantine_job, retry_job
from .models import DomainError
from .orchestrator import run_next
from .recordings import discover, publish_upload


def _remote_dependencies(config):
    from .orchestrator import _remote_dependencies as build
    return build(config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="field-transcriber")
    parser.add_argument("--config", default=Path("config.env"), type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--json", action="store_true", dest="as_json")
    publish = subparsers.add_parser("publish-upload")
    publish.add_argument("--staged-name", required=True)
    publish.add_argument("--original-name", required=True)
    publish.add_argument("--size", required=True, type=int)
    publish.add_argument("--sha256", required=True)
    publish.add_argument("--json", action="store_true", dest="as_json")
    discover_parser = subparsers.add_parser("discover")
    discover_parser.add_argument("--json", action="store_true", dest="as_json")
    status_parser = subparsers.add_parser("status")
    status_filter = status_parser.add_mutually_exclusive_group()
    status_filter.add_argument("--job", type=int)
    status_filter.add_argument("--recording")
    status_parser.add_argument("--json", action="store_true", dest="as_json")
    run_parser = subparsers.add_parser("run-next")
    run_parser.add_argument("--json", action="store_true", dest="as_json")
    retry_parser = subparsers.add_parser("retry")
    retry_parser.add_argument("--job", required=True, type=int)
    retry_parser.add_argument("--json", action="store_true", dest="as_json")
    quarantine_parser = subparsers.add_parser("quarantine")
    quarantine_parser.add_argument("--job", required=True, type=int)
    quarantine_parser.add_argument("--reason", required=True)
    quarantine_parser.add_argument("--json", action="store_true", dest="as_json")
    cancel_parser = subparsers.add_parser("cancel")
    cancel_parser.add_argument("--job", required=True, type=int)
    cancel_parser.add_argument("--json", action="store_true", dest="as_json")
    resolve_parser = subparsers.add_parser("resolve-remote")
    resolve_parser.add_argument("--job", required=True, type=int)
    resolve_parser.add_argument("--decision", required=True, choices=("wait", "abandon-retry"))
    resolve_parser.add_argument("--json", action="store_true", dest="as_json")
    cleanup_parser = subparsers.add_parser("cleanup-transfers")
    cleanup_parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(payload.get("message", payload.get("result", "ok")))


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        config = load_config(args.config)
        if args.command == "init":
            initialize(config)
            _emit({"result": "initialized", "message": f"initialized {config.root}"}, args.as_json)
            return 0
        if args.command == "publish-upload":
            recording = publish_upload(config, args.staged_name, args.original_name, args.size, args.sha256)
            _emit({"result": "published", "sha256": recording.sha256, "recording_id": recording.id, "path": str(recording.current_path)}, args.as_json)
            return 0
        if args.command == "discover":
            recordings = discover(config)
            _emit({"result": "discovered", "count": len(recordings), "recordings": [r.sha256 for r in recordings]}, args.as_json)
            return 0
        if args.command == "status":
            jobs = list_jobs(config, job_id=args.job, recording_digest=args.recording)
            _emit({"result": "status", "count": len(jobs), "jobs": jobs}, args.as_json)
            return 0
        if args.command == "run-next":
            result = run_next(config)
            _emit(result, args.as_json)
            return 0
        if args.command == "retry":
            retry_job(config, args.job)
            _emit({"result": "pending", "job_id": args.job}, args.as_json)
            return 0
        if args.command == "quarantine":
            destination = quarantine_job(config, args.job, args.reason)
            _emit({"result": "quarantined", "job_id": args.job, "path": str(destination)}, args.as_json)
            return 0
        if args.command == "cancel":
            from .remote import cancel_remote
            provider, store = _remote_dependencies(config)
            _emit(cancel_remote(config, provider, store, args.job), args.as_json)
            return 0
        if args.command == "resolve-remote":
            from .remote import resolve_remote
            _emit(resolve_remote(config, args.job, args.decision), args.as_json)
            return 0
        if args.command == "cleanup-transfers":
            from .remote import cleanup_transfers
            _, store = _remote_dependencies(config)
            outcomes = cleanup_transfers(config, store)
            _emit({"result": "cleanup", "count": len(outcomes), "objects": outcomes}, args.as_json)
            return 0
        raise AssertionError("unhandled command")
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except DomainError as exc:
        print(f"{exc.step}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
