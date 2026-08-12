# Quickstart Validation

This guide describes the checks that prove the first field-transcription workflow.
Commands are finalized during implementation; placeholders in angle brackets are
owner-supplied environment values.

## Prerequisites

- Repository checked out on the laptop and copied to
  `/home/assela/field-transcriber/code/` on the VPS.
- Passwordless SSH from the laptop to `<vps-host>`.
- VPS has Python 3.11, OpenSSH client/server, rsync, and sufficient file storage.
- Disposable worker has a compatible NVIDIA GPU/driver, Docker, NVIDIA Container
  Toolkit, and passwordless VPS-to-worker SSH for the rental session.
- Owner has accepted the `speaker-diarization-community-1` model conditions and has
  a read-only Hugging Face token available outside the repository.
- Dependencies are installed only after owner approval using the commands supplied
  by implementation documentation.

## 1. Deterministic local checks

From the repository root, run:

```bash
/home/assela/python/.venv/bin/python -m unittest discover -s tests -v
```

Expected: state transitions, claim expiry, duplicate/collision behavior,
transcript validation, and Markdown/SRT rendering tests pass without a GPU.

## 2. Initialize VPS storage

On the VPS:

```bash
cd /home/assela/field-transcriber/code
/home/assela/python/.venv/bin/python -m field_transcriber --config config.env init
/home/assela/python/.venv/bin/python -m field_transcriber --config config.env status
```

Expected: `uploading`, `incoming`, `processed`, `failed`, `transcripts`, and
`state` exist under `/home/assela/field-transcriber/files/`; an empty queue is
reported. If the VPS Python path differs, configure it explicitly in the uploader
without committing an environment-specific value.

## 3. Prove resumable, safe upload

From the laptop, start an upload of the representative MP3, interrupt it, then
repeat the same command:

```bash
local/upload.sh 260811_0111.MP3
```

Expected: the interrupted file exists only under `uploading/`; discovery cannot
register it. After resume and digest verification, it appears atomically in
`incoming/` and exactly one pending job exists. Repeating upload resolves to the
same recording/job.

## 4. Build and smoke-test the worker

On a compatible GPU worker, build the pinned image and run the project worker smoke
test according to `scripts/test-worker.sh`.

Expected: the container sees the GPU, loads the configured models, reads the input
mount without modifying it, and emits schema-valid JSON. Record the image identifier
used for the acceptance run.

Also run the worker against a silent fixture. Expected: the controller rejects the
zero-segment/textless result as `no_speech_detected`; no empty Markdown or SRT is
published, and the recording remains available for retry or quarantine.

## 5. Run one end-to-end job

On the VPS, supply worker connection values and the Hugging Face token through the
uncommitted runtime environment, then run:

```bash
cd /home/assela/field-transcriber/code
/home/assela/python/.venv/bin/python -m field_transcriber --config config.env run-next
```

Expected:

1. The pending job is claimed with a renewable expiry.
2. The VPS stages and starts the remote worker, renews the claim at least once per
   configured heartbeat interval, then pulls the canonical JSON.
3. JSON validation and Markdown/SRT rendering succeed.
4. The three transcript files are published below `files/transcripts/<sha256>/`.
5. The job is complete and the unchanged source is under `processed/`.
6. Remote job files are removed, or cleanup failure is clearly reported without
   reverting completion.

## 6. Owner acceptance review

Review the representative outdoor recording and Markdown/SRT outputs at passages
with wind, walking, distant speech, speaker changes, and overlap. Confirm that the
transcript is usable for following the conversation and locating audio passages,
and note limitations rather than editing the canonical JSON. Record wall time and
peak GPU memory for rental planning.

## 7. Failure recovery check

Interrupt one fake/local orchestration run after claim, allow its claim to expire,
and invoke `run-next` or `status` again. Confirm that the job becomes failed with an
interruption error. Then run `retry` and complete it once. At no point may the
source digest change or two active jobs exist for the recording.

See [CLI contract](contracts/cli.md), [data model](data-model.md), and
[transcript schema](contracts/transcript.schema.json) for precise expected behavior.

## Local validation record (2026-08-11)

- `/home/assela/python/.venv/bin/python -m unittest discover -s tests -v`:
  31 tests passed.
- Python byte-compilation: passed for `field_transcriber/` and `worker/`.
- Shell syntax: passed for upload, worker entrypoint, local/worker checks, and the
  guarded deployment helper.
- `git diff --check`: passed.
- Repository eligibility check: the representative `260811_0111.MP3` is ignored;
  no MP3/WAV, runtime `config.env`, database, or transcript path appears as eligible
  untracked content.
- Secret-pattern inspection: passed after excluding examples, specifications,
  tests, and the scanner's own regex definition.
- Docker image build/content inspection and rented-GPU acceptance: not run. They
  require explicit owner authorization, dependency/image downloads, a reachable
  GPU worker, and the gated-model token setup described above.
