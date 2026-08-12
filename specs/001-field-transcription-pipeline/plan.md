# Implementation Plan: Field Audio Transcription Pipeline

**Branch**: `001-field-transcription-pipeline` | **Date**: 2026-08-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-field-transcription-pipeline/spec.md`

## Summary

Build a small command-driven pipeline with three deployment surfaces: a resumable
laptop uploader, a dependency-light VPS controller backed by SQLite, and a
Dockerized disposable GPU worker. The VPS owns job state and initiates every worker
transfer. The worker uses WhisperX's faster-whisper backend, alignment, and
pyannote diarization to create one canonical JSON result; the VPS validates that
result and renders Markdown and SRT derivatives before atomically completing the
job and relocating its immutable source recording.

## Technical Context

**Language/Version**: Python 3.11 for controller, worker, renderers, and tests; POSIX-compatible Bash for upload/deployment wrappers  
**Primary Dependencies**: VPS controller uses Python standard library only; worker uses stable pinned WhisperX (faster-whisper backend), PyTorch/CUDA dependencies resolved in the image, pyannote `speaker-diarization-community-1`, FFmpeg, Docker, OpenSSH, and rsync  
**Storage**: SQLite 3 for recordings/jobs/attempts plus immutable MP3 and transcript files below `/home/assela/field-transcriber/files/`  
**Testing**: Python `unittest` for unit/contract tests; shell-driven local integration tests with temporary directories and fake SSH/worker commands; owner-run Docker/GPU acceptance check  
**Target Platform**: Laptop/WSL2 client; Linux VPS under user `assela`; disposable Linux NVIDIA worker with Docker, a compatible driver/runtime, and about 24 GB VRAM  
**Project Type**: Multi-surface CLI and batch-processing pipeline  
**Performance Goals**: Correct single-recording processing within one bounded GPU rental; record wall time and peak GPU memory during acceptance rather than impose an initial throughput target  
**Constraints**: Original MP3 immutable; VPS-controlled pull model; no return credential on worker; resumable/atomic upload; closed recoverable job states; JSON authoritative; no routine audio preprocessing; no new VPS service dependencies  
**Scale/Scope**: One owner, one controller, one active GPU job, tens to low hundreds of recordings per field campaign; no web UI or automatic GPU provisioning

## Constitution Check

*GATE: Passed before research and re-checked after design.*

- **Working path**: `upload -> discover -> claim -> stage worker -> transcribe ->
  pull result -> validate/render -> complete/relocate` is runnable through CLI
  commands. Local fake-worker validation precedes the owner-run GPU quickstart.
- **Data safety**: Upload staging and atomic publication prevent partial discovery.
  Recordings are keyed by SHA-256, opened read-only by processing code, and moved
  without content changes. JSON is canonical; Markdown and SRT are regenerated.
  SQLite transactions guard claims and completion.
- **Credential boundary**: Laptop credentials reach only the VPS. The VPS opens
  outbound SSH sessions and pulls results with `scp`; the worker receives no VPS
  key. A read-only Hugging Face token may be injected into the worker container
  solely to obtain gated diarization models.
- **Simple design**: The controller uses standard-library Python, SQLite, files,
  rsync, SSH, and SCP. There is no daemon requirement, API server, Redis, Celery,
  Kubernetes, or repository abstraction.
- **Testing**: Use test-first development where practical for state transitions,
  claims, digest collisions, schema validation, and renderers. Fake command runners
  cover failure paths. Real CUDA/model/audio behavior remains an owner-run check.
- **Proportionate validation**: Automated checks cover deterministic logic and
  local orchestration. The one representative outdoor recording is the only
  required GPU/audio-quality acceptance run.

Post-design re-check: all gates still pass. The CLI and JSON contracts make the
working path and boundary behavior testable without adding infrastructure.

## Design

### Controller boundaries

The controller is a Python package invoked as `python -m field_transcriber`.
Command handlers call small domain modules for discovery, state transitions,
worker orchestration, result validation, and rendering. SQLite writes use explicit
transactions. External commands are passed as argument arrays through one injected
command-runner boundary. That boundary supports both completed commands and a
pollable long-running process so integration tests can simulate rsync/SSH/SCP
outcomes and lease heartbeats.

### Upload publication

`local/upload.sh` transfers to `files/uploading/<name>.partial`, sends source size
and SHA-256 as arguments to a VPS-side `publish-upload` command, and lets that
command verify and atomically rename the file into `incoming/`. Discovery scans
only `incoming/`. A different file with the same name is rejected; the same digest
is treated as the existing recording even if its filename differs.

### Job lifecycle and recovery

SQLite stores the closed state set from the spec. Claiming uses a short transaction
that changes `pending` to `processing`, creates an attempt, and records a random
claim token plus expiry. The lease duration is configurable and defaults to five
minutes. During the blocking remote-worker command, the command runner polls the
child process and renews the lease every 60 seconds; other steps renew before and
after execution. Startup and `run-next` recover expired claims by recording an
interruption and moving the job to `failed`. If this controller cannot renew its
own claim, or discovers that the token/state no longer belongs to it, it stops
accepting results, attempts remote termination/cleanup, and returns a failure rather
than finalizing the job. `retry` is the only `failed -> pending` path.

### Worker protocol

The VPS creates a remote job directory, copies the MP3 and invokes a versioned
worker image through SSH. The container mounts one read-only input and one writable
output directory. It runs WhisperX with `large-v3`, CUDA/float16, VAD, forced
alignment, and `speaker-diarization-community-1`, then emits canonical JSON plus
run metadata. The VPS pulls output into a local staging directory and applies a
standard-library structural validator that mirrors the documentary JSON Schema.
Completion additionally requires at least one segment with non-whitespace text,
Markdown containing at least one rendered segment, and SRT containing at least one
timed cue. A zero-segment or textless result becomes a retryable failure with error
code `no_speech_detected`; it is not published as a completed transcript. After
validation, the VPS atomically publishes the three files, completes the SQLite
transaction, and moves the source to `processed/`. Cleanup is invoked remotely
afterward and recorded separately.

### Error handling

External-command failures capture step, exit status, and a bounded stderr excerpt.
No error path deletes or rewrites the permanent source. Invalid input may be
explicitly quarantined by the owner; ordinary worker/network failures leave the
recording in `incoming/` and the job retryable. A failure after verified completion
cannot reverse completion; cleanup failure is reported on the attempt.

## Project Structure

### Documentation (this feature)

```text
specs/001-field-transcription-pipeline/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   └── transcript.schema.json
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
field_transcriber/
├── __init__.py
├── __main__.py
├── cli.py
├── config.py
├── db.py
├── models.py
├── recordings.py
├── jobs.py
├── orchestrator.py
├── transcript.py
└── renderers.py
local/
├── upload.sh
└── config.example.env
worker/
├── Dockerfile
├── requirements.txt
├── entrypoint.sh
└── transcribe.py
scripts/
├── deploy-vps.sh
├── test-local.sh
└── test-worker.sh
tests/
├── fixtures/
├── test_cli.py
├── test_db.py
├── test_recordings.py
├── test_jobs.py
├── test_orchestrator.py
├── test_transcript.py
└── test_renderers.py
```

**Structure Decision**: One small Python controller package keeps domain behavior
testable while shell scripts remain thin entry points. The worker is isolated
because it has GPU-only dependencies and a separate container lifecycle.

## Complexity Tracking

No constitution violations require justification.
