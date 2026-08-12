# CLI Contract Additions

Existing commands and exit-code conventions remain unchanged.

## Configuration

`FIELD_TRANSCRIBER_WORKER_MODE=ssh|runpod` selects execution mode. Runpod endpoint,
API-key environment-variable name, execution/TTL values, polling settings, and
S3-compatible endpoint/bucket/region/access-key environment-variable names are
configured without committing secrets.

## `run-next`

In `runpod` mode, `run-next` first reconciles any processing remote execution. It
submits a new job only when no active or indeterminate remote execution exists.
Reconciliation probes the known result object before provider status and
re-establishes the existing attempt's local claim when status is queued/running.
JSON output includes local job ID, provider, external job ID when known, normalized
remote state, and final cleanup state; it excludes credentials and signed URLs.

## `cancel --job ID`

Cancels the active remote execution for one job. The command queries authoritative
status after cancellation. A concurrently completed valid result is accepted and
completed locally; otherwise the job becomes failed/cancelled and remains eligible
for explicit retry.

## `resolve-remote --job ID --decision wait|abandon-retry`

Available only for an indeterminate execution after its configured reconciliation
deadline. `wait` records the decision and extends reconciliation. `abandon-retry`
records owner authorization, makes the local job failed/retryable, and never
deletes the original recording. Neither decision submits a new remote job.

## `cleanup-transfers`

Deletes transfer objects whose failed-attempt retention period expired and retries
objects marked `cleanup_failed`. It is idempotent and reports per-object outcomes.
`run-next` performs the same due cleanup opportunistically before processing work.
