# Project Working Agreements

## Environment

- Work from the repository root.
- Use `python3` for the dependency-free SDD orchestration script.
- Do not install dependencies or system packages without owner approval.
- Keep secrets and environment-specific values out of version control.

## Development Workflow

- Inspect the project before changing it.
- Make minimal, focused changes and reuse existing code before adding abstractions.
- Prefer a focused failing test before implementing important or failure-prone behavior.
  For small scripts, configuration, and exploratory integration work, a test added
  alongside the change or a documented manual check is acceptable.
- Run the smallest relevant validation after changes and report skipped checks.
- Aim for a dependable working tool, not production-grade process or exhaustive
  coverage. Spend effort in proportion to the risk and cost of failure.
- Do not commit, push, deploy, or run destructive commands unless explicitly requested.

## SDD Workflow

- Codex owns specification, plan, tasks, implementation, and revisions.
- Claude Code independently reviews each published stage.
- Use `$start-sdd <feature description>` in Codex and `/review-sdd` in Claude Code.
- Treat `.ai-flow/` as local runtime state; never edit its marker files manually.

## Project-Specific Guidance

- This is a small field-audio transcription pipeline, primarily operated through
  Python and shell commands on WSL2, a persistent Linux VPS, and a disposable
  NVIDIA GPU worker.
- Follow the architecture and scope in `idea.txt`. Keep the VPS controller and
  SQLite job queue lightweight; do not introduce Celery, Redis, Kubernetes, or a
  web application unless a concrete need emerges.
- Preserve each original MP3 unchanged. Transcription and optional LLM analysis
  are separate stages, and generated interpretation must never replace the
  authoritative transcript.
- The VPS initiates transfers and work on the GPU node. The disposable GPU worker
  must not contain credentials that grant access back to the VPS, and images or
  committed files must not contain credentials or field data.
- Prioritize a working end-to-end path, restartable/idempotent job handling,
  useful failure messages, retryability, and verified result transfer.
- Use `faster-whisper` with Whisper `large-v3`, word timestamps and VAD, plus
  WhisperX/pyannote diarization, unless testing reveals a practical reason to
  revise the approach.
- Expected outputs for each recording are authoritative JSON plus readable
  Markdown and SRT derivatives. Speaker labels may remain anonymous identifiers.
- Test pure logic and job-state transitions with focused automated tests. Use a
  small representative recording for integration checks. Full outdoor-audio and
  rented-GPU validation can be an explicit owner-run acceptance check rather than
  part of every development cycle.
- Do not require production-grade observability, scalability, hardening, rollback
  plans, exhaustive edge-case coverage, or formal performance evidence unless a
  feature specifically needs them.
- Use `python3` only for the dependency-free SDD orchestration script. For project
  Python commands, use `/home/assela/python/.venv/bin/python` and its `-m pip`
  form. Do not install missing dependencies; report the exact installation command.

## Active Technologies
- Python 3.11 for controller, worker, renderers, and tests; POSIX-compatible Bash for upload/deployment wrappers + VPS controller uses Python standard library only; worker uses stable pinned WhisperX (faster-whisper backend), PyTorch/CUDA dependencies resolved in the image, pyannote `speaker-diarization-community-1`, FFmpeg, Docker, OpenSSH, and rsync (001-field-transcription-pipeline)
- SQLite 3 for recordings/jobs/attempts plus immutable MP3 and transcript files below `/home/assela/field-transcriber/files/` (001-field-transcription-pipeline)

## Recent Changes
- 001-field-transcription-pipeline: Added Python 3.11 for controller, worker, renderers, and tests; POSIX-compatible Bash for upload/deployment wrappers + VPS controller uses Python standard library only; worker uses stable pinned WhisperX (faster-whisper backend), PyTorch/CUDA dependencies resolved in the image, pyannote `speaker-diarization-community-1`, FFmpeg, Docker, OpenSSH, and rsync
