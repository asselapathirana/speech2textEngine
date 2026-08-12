# Architecture

## Data flow

```text
Olympus recorder
  -> laptop/WSL2 backup
  -> resumable SSH upload
  -> VPS staging and SHA-256 publication
  -> SQLite pending job
  -> VPS-controlled disposable GPU run
  -> VPS result pull and validation
  -> canonical JSON + Markdown + SRT
```

The permanent trust boundary ends at the VPS. The VPS holds original recordings,
job state, transcripts, and its outbound worker credential. The worker receives
one input recording, a narrowly scoped Hugging Face read token, and a public worker
image. It never receives a VPS key or a callback endpoint.

## Controller

The `field_transcriber` package uses only Python's standard library. `db.py` owns
SQLite setup and transactions. `recordings.py` owns immutable source lifecycle.
`jobs.py` owns the closed state machine and token-guarded claims. `orchestrator.py`
owns SSH/SCP steps and heartbeat renewal. `transcript.py` validates the fixed v1
document shape; `renderers.py` creates and atomically publishes derivatives.

External commands cross one injectable command-runner boundary. Errors retain a
bounded, redacted diagnostic and the step at which they occurred.

## State and recovery

```text
pending -> processing -> complete
                    \-> failed -> pending
```

Claims default to a five-minute lease and renew every minute. Recovery marks an
expired processing claim failed. Only `retry` returns it to pending. Completion is
token-guarded and requires valid, non-empty JSON, Markdown, and SRT. The source is
moved to `processed/` without changing its digest.

If interruption occurs after file publication or source movement but before the
SQLite update, completion code checks the expected outputs and current source path
before repeating actions. It never replaces a valid transcript silently.

## Upload identity

The uploader writes `<name>.partial` below `uploading/`. The VPS verifies expected
size and SHA-256, then uses an atomic rename into `incoming/`. Discovery never scans
the staging directory. SHA-256 is stable identity across names and lifecycle paths;
a same-name/different-content collision requires owner intervention.

## Worker

The pinned image runs WhisperX 3.8.6 with `large-v3`, CUDA float16, VAD, forced
alignment, and the pyannote `speaker-diarization-community-1` model. Input is mounted
read-only and JSON output is atomically renamed after serialization. Optional
pyannote telemetry is disabled.

The image contains code and dependencies only. `scripts/test-worker.sh` requires an
explicit build opt-in and inspects image history and files for likely secrets or
field data before its GPU smoke check.
