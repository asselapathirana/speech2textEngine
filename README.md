# Field Transcriber

Field Transcriber moves original Olympus WS-852 MP3 recordings from a laptop to a
persistent VPS, processes one recording at a time on a disposable NVIDIA GPU
worker, and stores an authoritative JSON transcript plus Markdown and SRT views.

This is an owner-operated tool. It deliberately uses a small Python/SQLite
controller and SSH transfers rather than a web service or distributed queue.

## Safety properties

- Uploads remain under `uploading/` until size and SHA-256 verification publishes
  them atomically into `incoming/`.
- Original MP3 content is never rewritten. Successful inputs move to `processed/`;
  owner-quarantined input moves to `failed/`.
- The VPS initiates worker transfers, execution, result retrieval, and cleanup.
  The worker receives no credential that authenticates back to the VPS.
- JSON is authoritative. Markdown and SRT are deterministic derivatives.
- Claims expire and can be recovered; a controller renews its claim while a remote
  transcription is running.

## Repository layout

```text
field_transcriber/   dependency-free VPS controller
local/               laptop uploader and example configuration
worker/              disposable GPU container
scripts/             validation and code-only deployment helpers
tests/               dependency-free controller/contract tests
specs/               approved feature specification and design
```

On the VPS, code and data are kept apart:

```text
/home/assela/field-transcriber/
├── code/
└── files/
    ├── uploading/
    ├── incoming/
    ├── processed/
    ├── failed/
    ├── transcripts/
    └── state/
```

## Local validation

The controller tests require no external Python packages:

```bash
/home/assela/python/.venv/bin/python -m unittest discover -s tests -v
```

Shell syntax checks:

```bash
sh -n local/upload.sh worker/entrypoint.sh scripts/test-local.sh scripts/test-worker.sh scripts/deploy-vps.sh
```

## Configuration and operation

For the normal laptop workflow, copy `local/config.example.env` to the untracked
`local/config.env` once, then run one command:

```bash
local/transcribe.py /path/to/recording.mp3
local/transcribe.py '/path/to/recordings/*.mp3'
```

The command accepts any MP3 path and one or more wildcard patterns. Quote a
pattern so the script expands it consistently. It processes matches sequentially
and saves `<name>.transcript.json`, `<name>.transcript.md`, and
`<name>.transcript.srt` beside each original MP3. It submits or resumes each
Runpod job and prints state changes while waiting. The terminal must remain open
while the VPS controller is running. Re-running the command is safe and downloads
an already completed result without starting another GPU job. Spaces and other
unsafe characters are sanitized only in the remote copy; the original is unchanged.

The individual operating steps remain available for diagnosis:

1. Copy `config.example.env` to an untracked `config.env` on the VPS and edit the
   worker connection values.
2. Copy `local/config.example.env` to untracked `local/config.env` on the laptop.
3. Initialize VPS directories and state:

   ```bash
   python3 -m field_transcriber --config config.env init
   ```

4. Upload a recording from the laptop:

   ```bash
   local/upload.sh /path/to/recording.mp3
   ```

5. On the VPS, provide the read-only Hugging Face token named by
   `FIELD_TRANSCRIBER_HF_TOKEN_ENV`, then process one pending job:

   ```bash
   python3 -m field_transcriber --config config.env run-next
   ```

Use `status --json`, `retry --job ID`, and `quarantine --job ID --reason TEXT` for
inspection and recovery. See [architecture](docs/architecture.md) and the
[validation quickstart](specs/001-field-transcription-pipeline/quickstart.md).

## External prerequisites

The laptop/VPS path needs `rsync`, OpenSSH, Python, and SQLite support from Python's
standard library. The disposable worker needs Docker, a compatible NVIDIA driver
and runtime, and access to download the pinned worker dependencies and gated
pyannote model. This repository does not install host packages or rent a worker.

## Known limitations

- One active GPU job at a time; no automatic GPU provisioning or shutdown.
- Diarization and overlapping speech can be inaccurate.
- Alignment depends on language-specific models. Some words may lack timestamps.
- A speechless result is a retryable `no_speech_detected` failure, not an empty
  completed transcript.
- Worker cleanup is best-effort; disposable nodes should still be destroyed by the
  owner after the rental session.
# Serverless Runpod mode

Set `FIELD_TRANSCRIBER_WORKER_MODE=runpod` to use queue-based disposable GPU
execution. Configure the endpoint and S3-compatible transient bucket using
`config.example.env`; configuration stores only the names of runtime secret
environment variables. `run-next` uploads one attempt-qualified input, submits an
asynchronous job, polls through the provider-neutral lifecycle, validates and
publishes JSON/Markdown/SRT locally, and deletes transient objects. The default
execution timeout is two hours and TTL is three hours; both are configurable.

Operational recovery commands are `cancel --job ID`, `resolve-remote --job ID
--decision wait|abandon-retry`, and `cleanup-transfers`. Select `ssh` mode to use
the previous worker path during migration or provider outages. A real Runpod run
requires separate authorization because it incurs charges and transfers audio.
