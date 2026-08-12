# CLI Contract

All controller commands are invoked from the repository code directory as:

```text
python -m field_transcriber [--config PATH] COMMAND [OPTIONS]
```

Successful commands exit `0`. Usage/configuration errors exit `2`. Operational
failures exit `1` and write one concise message to stderr without secret values.
Machine-consumable commands support `--json` and emit exactly one JSON document.

## Laptop uploader

```text
local/upload.sh SOURCE_MP3
```

Transfers to the configured VPS `uploading/` path with resumable partial data,
computes source size and SHA-256, then invokes `publish-upload`. Repeating the same
command is safe. It prints the resulting recording digest and disposition.

## Controller commands

### `init`

```text
python -m field_transcriber init
```

Creates configured directories and the SQLite schema. Repeated invocation is safe.

### `publish-upload`

```text
python -m field_transcriber publish-upload \
  --staged-name NAME.partial --original-name NAME.mp3 \
  --size SIZE_BYTES --sha256 HEX_DIGEST [--json]
```

Verifies the staged file, atomically publishes it, and creates or resolves its
Recording and Job. An incomplete staged file remains untouched and is not
registered. A filename collision with different content fails.

### `discover`

```text
python -m field_transcriber discover [--json]
```

Registers verified, unregistered files already present in `incoming/`. It never
scans `uploading/` and is idempotent by digest.

### `status`

```text
python -m field_transcriber status [--job ID | --recording SHA256] [--json]
```

Shows recording location, job state, attempts, claim expiry where applicable, and
the latest error. It never prints credentials.

### `run-next`

```text
python -m field_transcriber run-next [--json]
```

Recovers expired claims, atomically claims the oldest pending job, executes one
worker run, pulls and validates results, renders derivatives, finalizes state, and
attempts worker cleanup. If no job is pending, exits successfully with a `no_job`
result. While the remote worker runs, the controller renews its token-guarded claim
at the configured heartbeat interval. Loss of claim ownership stops result
acceptance and triggers best-effort remote termination/cleanup.

### `retry`

```text
python -m field_transcriber retry --job ID [--json]
```

Changes exactly one failed job to pending. Other current states are rejected.

### `quarantine`

```text
python -m field_transcriber quarantine --job ID --reason TEXT [--json]
```

Moves the immutable input of a failed job from `incoming/` to `failed/`, updates
its Recording disposition/path, and retains diagnostics. It does not delete data.

## Worker entrypoint

```text
/app/entrypoint.sh --input /input/recording.mp3 \
  --output /output/transcript.json --recording-sha256 HEX_DIGEST
```

The input mount is read-only. Output is written to a temporary name and renamed to
`transcript.json` only after serialization succeeds. The worker exits nonzero on
transcription, alignment, diarization, or serialization failure and writes no VPS
credentials or transcript content to stdout/stderr.

## Transcript validation contract

`transcript.schema.json` documents the fixed v1 wire shape and supplies fixtures
for contract tests. Runtime validation uses Python standard-library type, key,
range, ordering, and content checks rather than a JSON Schema library. These checks
must remain behaviorally aligned with the schema.

Completion additionally requires:

- at least one segment with non-whitespace text;
- finite, non-negative segment times with `end >= start`, in chronological order;
- each timed word to have finite, non-negative values with `end >= start`;
- rendered Markdown with at least one speaker/timestamp segment line; and
- rendered SRT with at least one numbered cue and valid time range.

A structurally valid result with no qualifying segment fails the attempt with
`no_speech_detected`. It is not published and leaves the recording retryable.
