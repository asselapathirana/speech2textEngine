# Research: Disposable Serverless GPU Execution

## Runpod job lifecycle and limits

**Decision**: Use queue-based asynchronous `/run` jobs with per-request
`executionTimeout=7200000` and `ttl=10800000`; poll `/status/{id}`, cancel through
`/cancel/{id}`, and configure zero active workers with maximum one worker.

**Rationale**: Official Runpod documentation allows both limits up to seven days,
retains async results for 30 minutes, defaults active workers to zero, and supports
a short idle timeout. This meets the required safety ceiling without extending
normal billing when work finishes early.

**Alternatives considered**: Synchronous `/runsync` (fragile for long jobs and
one-minute result retention); manually created Pods (more lifecycle and orphan
cleanup code); load-balancing endpoints (no queue/retry lifecycle benefit).

## Provider portability

**Decision**: Define `submit`, `status`, and `cancel` operations returning a closed
provider-neutral state set. Keep Runpod URLs, status names, and response fields in
one adapter.

**Rationale**: The existing transcript and job domains should not know Runpod. A
fake adapter can exercise all recovery logic and a future provider can replace the
adapter without changing transcription.

**Alternatives considered**: Calling Runpod directly from `orchestrator.py`
(smaller initially but locks state/retry logic to Runpod); adopting a cloud SDK in
the controller (new dependency with little benefit over a small HTTP adapter).

## Temporary object transfer

**Decision**: Use an owner-configured S3-compatible bucket. The VPS implements
AWS Signature Version 4 with the Python standard library, uploads the source,
creates one-object presigned GET/PUT URLs, downloads the result, and deletes both
objects after verified publication.

**Rationale**: Large audio should not travel in Runpod JSON. Presigned URLs keep
bucket credentials and VPS credentials off the worker while working with several
storage providers. Standard-library signing preserves the lightweight controller.

**Alternatives considered**: Runpod `s3Config` (passes reusable bucket credentials
to the worker); network volumes (persistent, region-bound, and unnecessary);
temporary HTTP service on the VPS (adds inbound networking and an endpoint);
embedding base64 audio in requests (size and memory overhead).

## Remote state and restart recovery

**Decision**: Persist one remote-execution row per local attempt before polling.
Reconcile all processing jobs with remote identities before expired-claim recovery
or new claims. Probe the known result object before provider status; a valid,
digest-matching result is success even after provider status retention expires.
For queued/running status, atomically mint a replacement local claim token and
lease on the same attempt before expired-claim recovery. Keep genuinely
indeterminate submissions blocked until explicit owner action.

**Rationale**: Feature 001 showed that ordering around claims and external effects
is the main reliability risk. Durable external identity prevents duplicate paid
work and lets normal startup perform recovery.

**Alternatives considered**: Treat controller interruption as ordinary failure
(can duplicate a still-running job); keep remote ID only in memory (not
restartable); automatically retry after a timer (can double-charge).

## Worker integration

**Decision**: Add a thin `worker/serverless.py` wrapper that validates input,
downloads and digest-checks the MP3, calls the existing `transcribe` function,
uploads canonical JSON, and returns a bounded manifest. Use the Runpod worker SDK
only in this wrapper.

**Rationale**: The expensive model pipeline remains provider-neutral and directly
testable. The SDK is necessary for Runpod's queue handler lifecycle but does not
belong in controller or domain modules.

**Alternatives considered**: Rewriting transcription inside a handler (duplicate
logic); invoking the CLI through a subprocess (more indirection and weaker error
typing).

## Webhooks

**Decision**: Defer webhooks. Polling is the sole required completion path.

**Rationale**: Webhooks add an inbound VPS endpoint, authentication, replay, and
deployment concerns without being necessary for one long-running job at a time.

**Alternatives considered**: Authenticated webhook plus polling fallback (valid at
larger scale, unnecessary here).
