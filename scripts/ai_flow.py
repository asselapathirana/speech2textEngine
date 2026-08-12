#!/usr/bin/env python3
"""Coordinate a resumable file-based SDD review workflow across two CLIs."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

STAGES = ("spec", "plan", "tasks", "implementation")
STATUSES = ("APPROVED", "CHANGES_REQUIRED", "HUMAN_REVIEW")
STATE_VERSION = 1
DEFAULT_MAX_ROUNDS = 4
DEFAULT_POLL_SECONDS = 2.0
REPO_ROOT = Path(__file__).resolve().parent.parent


class FlowError(RuntimeError):
    """Raised when the orchestration state violates the protocol."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def flow_dir_from_args(args: argparse.Namespace) -> Path:
    configured = args.flow_dir or os.environ.get("AI_FLOW_DIR")
    return Path(configured).resolve() if configured else REPO_ROOT / ".ai-flow"


def state_path(flow_dir: Path) -> Path:
    return flow_dir / "flow.json"


def marker_path(flow_dir: Path, stage: str, suffix: str) -> Path:
    return flow_dir / f"{stage}.{suffix}"


def review_path(flow_dir: Path, stage: str) -> Path:
    return flow_dir / f"{stage}-review.md"


def review_status_path(flow_dir: Path, stage: str) -> Path:
    return flow_dir / f"{stage}-review.status"


def iteration_path(flow_dir: Path, stage: str) -> Path:
    return flow_dir / f"{stage}.iteration"


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: dict[str, object]) -> None:
    atomic_write_text(path, f"{json.dumps(value, indent=2, sort_keys=True)}\n")


@contextmanager
def locked(flow_dir: Path) -> Iterator[None]:
    flow_dir.mkdir(parents=True, exist_ok=True)
    with (flow_dir / ".lock").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def default_state(max_rounds: int) -> dict[str, object]:
    return {
        "version": STATE_VERSION,
        "state": "active",
        "current_stage": None,
        "max_rounds": max_rounds,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "stages": {
            stage: {
                "iteration": 0,
                "round_limit": max_rounds,
                "status": "pending",
            }
            for stage in STAGES
        },
    }


def load_state(flow_dir: Path) -> dict[str, object]:
    path = state_path(flow_dir)
    if not path.exists():
        raise FlowError(f"No flow exists in {flow_dir}. Run `ai_flow.py init` first.")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise FlowError(f"Cannot read orchestration state: {error}") from error
    if state.get("version") != STATE_VERSION:
        raise FlowError(
            f"Unsupported orchestration state version: {state.get('version')}"
        )
    return state


def save_state(flow_dir: Path, state: dict[str, object]) -> None:
    state["updated_at"] = utc_now()
    atomic_write_json(state_path(flow_dir), state)


def stage_record(state: dict[str, object], stage: str) -> dict[str, object]:
    stages = state["stages"]
    if not isinstance(stages, dict):
        raise FlowError("Invalid stage state.")
    record = stages.get(stage)
    if not isinstance(record, dict):
        raise FlowError(f"Missing state for stage {stage}.")
    return record


def validate_stage(stage: str) -> None:
    if stage not in STAGES:
        raise FlowError(
            f"Unknown stage {stage!r}; expected one of {', '.join(STAGES)}."
        )


def validate_status(status: str) -> None:
    if status not in STATUSES:
        raise FlowError(
            f"Unknown status {status!r}; expected one of {', '.join(STATUSES)}."
        )


def prior_stage(stage: str) -> str | None:
    index = STAGES.index(stage)
    return STAGES[index - 1] if index else None


def output_json(value: dict[str, object]) -> None:
    print(json.dumps(value, sort_keys=True))


def command_init(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    if args.max_rounds < 1:
        raise FlowError("--max-rounds must be at least 1.")
    with locked(flow_dir):
        if state_path(flow_dir).exists():
            state = load_state(flow_dir)
            output_json({"result": "resumed", "flow_dir": str(flow_dir), **state})
            return
        state = default_state(args.max_rounds)
        save_state(flow_dir, state)
        output_json({"result": "initialized", "flow_dir": str(flow_dir), **state})


def archive_prior_review(flow_dir: Path, stage: str, iteration: int) -> None:
    source = review_path(flow_dir, stage)
    if not source.exists() or not source.read_text(encoding="utf-8").strip():
        return
    history = flow_dir / "history"
    history.mkdir(parents=True, exist_ok=True)
    destination = history / f"{stage}-review-round-{iteration:03d}.md"
    if not destination.exists():
        shutil.copy2(source, destination)


def validate_review_report(report: Path, status: str) -> None:
    if not report.exists():
        raise FlowError(f"Review report {report} is missing.")
    lines = report.read_text(encoding="utf-8").splitlines()
    try:
        verdict_heading = lines.index("## Verdict")
    except ValueError as error:
        raise FlowError(
            f"Review report {report} has no `## Verdict` heading."
        ) from error
    verdict = next(
        (line.strip() for line in lines[verdict_heading + 1 :] if line.strip()),
        None,
    )
    if verdict != status:
        raise FlowError(f"Review report verdict is {verdict!r}; expected {status!r}.")


def command_publish(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    stage = args.stage
    validate_stage(stage)
    with locked(flow_dir):
        state = load_state(flow_dir)
        if state["state"] == "complete":
            raise FlowError("The flow is already complete.")
        previous = prior_stage(stage)
        if previous and stage_record(state, previous)["status"] != "approved":
            raise FlowError(f"Cannot publish {stage} before {previous} is approved.")
        ready = marker_path(flow_dir, stage, "ready")
        reviewing = marker_path(flow_dir, stage, "reviewing")
        if ready.exists() or reviewing.exists():
            raise FlowError(f"Stage {stage} is already ready or under review.")
        record = stage_record(state, stage)
        prior_iteration = int(record["iteration"])
        archive_prior_review(flow_dir, stage, prior_iteration)
        iteration = prior_iteration + 1
        round_limit = int(record.get("round_limit", state["max_rounds"]))
        review_status_path(flow_dir, stage).unlink(missing_ok=True)
        if iteration > round_limit:
            atomic_write_text(review_status_path(flow_dir, stage), "HUMAN_REVIEW\n")
            record.update({"iteration": iteration, "status": "human_review"})
            state.update({"state": "human_review", "current_stage": stage})
            save_state(flow_dir, state)
            output_json(
                {
                    "stage": stage,
                    "iteration": iteration,
                    "status": "HUMAN_REVIEW",
                    "reason": "maximum review rounds exceeded",
                }
            )
            return
        marker = {
            "stage": stage,
            "iteration": iteration,
            "published_at": utc_now(),
        }
        atomic_write_text(iteration_path(flow_dir, stage), f"{iteration}\n")
        atomic_write_json(ready, marker)
        record.update({"iteration": iteration, "status": "waiting_review"})
        state.update({"state": "active", "current_stage": stage})
        save_state(flow_dir, state)
        output_json({"status": "READY", **marker})


def find_claimable_stage(
    flow_dir: Path, requested_stage: str | None
) -> tuple[str, str]:
    stages = (requested_stage,) if requested_stage else STAGES
    for stage in stages:
        reviewing = marker_path(flow_dir, stage, "reviewing")
        if reviewing.exists():
            return stage, "resumed"
    for stage in stages:
        ready = marker_path(flow_dir, stage, "ready")
        if ready.exists():
            os.replace(ready, marker_path(flow_dir, stage, "reviewing"))
            return stage, "claimed"
    raise FileNotFoundError


def wait_until(deadline: float | None, poll_seconds: float) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise FlowError("Timed out waiting for orchestration state.")
    time.sleep(poll_seconds)


def command_claim(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    if args.stage:
        validate_stage(args.stage)
    deadline = time.monotonic() + args.timeout if args.timeout else None
    while True:
        with locked(flow_dir):
            if not state_path(flow_dir).exists():
                state = None
            else:
                state = load_state(flow_dir)
            if state is None:
                pass
            elif state["state"] in {"complete", "human_review"}:
                output_json(
                    {
                        "result": "terminal",
                        "state": state["state"],
                        "current_stage": state["current_stage"],
                    }
                )
                return
            else:
                try:
                    stage, result = find_claimable_stage(flow_dir, args.stage)
                except FileNotFoundError:
                    pass
                else:
                    record = stage_record(state, stage)
                    record["status"] = "reviewing"
                    state["current_stage"] = stage
                    save_state(flow_dir, state)
                    output_json(
                        {
                            "result": result,
                            "stage": stage,
                            "iteration": record["iteration"],
                        }
                    )
                    return
        wait_until(deadline, args.poll)


def command_complete(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    stage = args.stage
    requested_status = args.status
    validate_stage(stage)
    validate_status(requested_status)
    with locked(flow_dir):
        state = load_state(flow_dir)
        reviewing = marker_path(flow_dir, stage, "reviewing")
        if not reviewing.exists():
            raise FlowError(f"Stage {stage} is not claimed for review.")
        report = review_path(flow_dir, stage)
        validate_review_report(report, requested_status)
        record = stage_record(state, stage)
        iteration = int(record["iteration"])
        round_limit = int(record.get("round_limit", state["max_rounds"]))
        final_status = requested_status
        if requested_status == "CHANGES_REQUIRED" and iteration >= round_limit:
            final_status = "HUMAN_REVIEW"
        atomic_write_text(review_status_path(flow_dir, stage), f"{final_status}\n")
        reviewing.unlink()
        state_status = {
            "APPROVED": "approved",
            "CHANGES_REQUIRED": "changes_requested",
            "HUMAN_REVIEW": "human_review",
        }[final_status]
        record["status"] = state_status
        state["current_stage"] = stage
        state["state"] = "human_review" if final_status == "HUMAN_REVIEW" else "active"
        save_state(flow_dir, state)
        output_json(
            {
                "stage": stage,
                "iteration": iteration,
                "requested_status": requested_status,
                "status": final_status,
            }
        )


def command_wait_review(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    stage = args.stage
    validate_stage(stage)
    deadline = time.monotonic() + args.timeout if args.timeout else None
    status_path = review_status_path(flow_dir, stage)
    while True:
        with locked(flow_dir):
            state = load_state(flow_dir)
            if status_path.exists():
                status = status_path.read_text(encoding="utf-8").strip()
                validate_status(status)
                if args.value_only:
                    print(status)
                else:
                    output_json(
                        {
                            "stage": stage,
                            "iteration": stage_record(state, stage)["iteration"],
                            "status": status,
                            "report": str(review_path(flow_dir, stage)),
                        }
                    )
                return
        wait_until(deadline, args.poll)


def command_release(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    stage = args.stage
    validate_stage(stage)
    with locked(flow_dir):
        state = load_state(flow_dir)
        reviewing = marker_path(flow_dir, stage, "reviewing")
        if not reviewing.exists():
            raise FlowError(f"Stage {stage} is not claimed for review.")
        os.replace(reviewing, marker_path(flow_dir, stage, "ready"))
        stage_record(state, stage)["status"] = "waiting_review"
        save_state(flow_dir, state)
        output_json({"stage": stage, "status": "READY", "result": "released"})


def command_resolve(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    stage = args.stage
    status = args.status
    validate_stage(stage)
    with locked(flow_dir):
        state = load_state(flow_dir)
        record = stage_record(state, stage)
        if state["state"] != "human_review" or record["status"] != "human_review":
            raise FlowError(f"Stage {stage} is not awaiting human review.")
        if (
            marker_path(flow_dir, stage, "ready").exists()
            or marker_path(flow_dir, stage, "reviewing").exists()
        ):
            raise FlowError(f"Stage {stage} still has an active review marker.")
        atomic_write_text(review_status_path(flow_dir, stage), f"{status}\n")
        record["status"] = {
            "APPROVED": "approved",
            "CHANGES_REQUIRED": "changes_requested",
        }[status]
        if status == "CHANGES_REQUIRED":
            iteration = int(record["iteration"])
            round_limit = int(record.get("round_limit", state["max_rounds"]))
            if iteration >= round_limit:
                record["round_limit"] = iteration + 1
        state["state"] = "active"
        state["current_stage"] = stage
        save_state(flow_dir, state)
        output_json(
            {
                "stage": stage,
                "iteration": record["iteration"],
                "status": status,
                "result": "human_review_resolved",
            }
        )


def command_finish(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    with locked(flow_dir):
        state = load_state(flow_dir)
        incomplete = [
            stage
            for stage in STAGES
            if stage_record(state, stage)["status"] != "approved"
        ]
        if incomplete:
            raise FlowError(
                f"Cannot finish; stages not approved: {', '.join(incomplete)}."
            )
        state.update(
            {
                "state": "complete",
                "current_stage": "implementation",
                "completed_at": utc_now(),
            }
        )
        save_state(flow_dir, state)
        output_json({"state": "complete", "flow_dir": str(flow_dir)})


def command_status(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    with locked(flow_dir):
        state = load_state(flow_dir)
        output_json({"flow_dir": str(flow_dir), **state})


def command_reset(args: argparse.Namespace) -> None:
    flow_dir = flow_dir_from_args(args)
    if not args.confirm:
        raise FlowError("Reset requires --confirm.")
    if args.max_rounds < 1:
        raise FlowError("--max-rounds must be at least 1.")
    with locked(flow_dir):
        if flow_dir.exists():
            for path in flow_dir.iterdir():
                if path.name == ".lock":
                    continue
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        state = default_state(args.max_rounds)
        save_state(flow_dir, state)
        output_json({"result": "reset", "flow_dir": str(flow_dir), **state})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flow-dir",
        help="Runtime directory; defaults to AI_FLOW_DIR or <repo>/.ai-flow.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize or resume a flow.")
    init_parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    init_parser.set_defaults(handler=command_init)

    publish_parser = subparsers.add_parser(
        "publish", help="Publish one stage for review."
    )
    publish_parser.add_argument("stage", choices=STAGES)
    publish_parser.set_defaults(handler=command_publish)

    claim_parser = subparsers.add_parser(
        "claim", help="Wait for and atomically claim the next ready stage."
    )
    claim_parser.add_argument("--stage", choices=STAGES)
    claim_parser.add_argument("--timeout", type=float, default=0)
    claim_parser.add_argument("--poll", type=float, default=DEFAULT_POLL_SECONDS)
    claim_parser.set_defaults(handler=command_claim)

    complete_parser = subparsers.add_parser(
        "complete", help="Publish a completed review status."
    )
    complete_parser.add_argument("stage", choices=STAGES)
    complete_parser.add_argument("status", choices=STATUSES)
    complete_parser.set_defaults(handler=command_complete)

    wait_parser = subparsers.add_parser(
        "wait-review", help="Wait for a machine-readable review status."
    )
    wait_parser.add_argument("stage", choices=STAGES)
    wait_parser.add_argument("--timeout", type=float, default=0)
    wait_parser.add_argument("--poll", type=float, default=DEFAULT_POLL_SECONDS)
    wait_parser.add_argument("--value-only", action="store_true")
    wait_parser.set_defaults(handler=command_wait_review)

    release_parser = subparsers.add_parser(
        "release", help="Return an interrupted review claim to ready."
    )
    release_parser.add_argument("stage", choices=STAGES)
    release_parser.set_defaults(handler=command_release)

    resolve_parser = subparsers.add_parser(
        "resolve-human", help="Apply the owner's decision after a human-review stop."
    )
    resolve_parser.add_argument("stage", choices=STAGES)
    resolve_parser.add_argument("status", choices=("APPROVED", "CHANGES_REQUIRED"))
    resolve_parser.set_defaults(handler=command_resolve)

    finish_parser = subparsers.add_parser(
        "finish", help="Mark a fully approved flow complete."
    )
    finish_parser.set_defaults(handler=command_finish)

    status_parser = subparsers.add_parser("status", help="Print current flow state.")
    status_parser.set_defaults(handler=command_status)

    reset_parser = subparsers.add_parser(
        "reset", help="Reset runtime state while preserving the directory."
    )
    reset_parser.add_argument("--confirm", action="store_true")
    reset_parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    reset_parser.set_defaults(handler=command_reset)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handler(args)
    except (FlowError, OSError, ValueError) as error:
        print(f"ai-flow: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
