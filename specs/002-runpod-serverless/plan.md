# Implementation Plan: Disposable Serverless GPU Execution

**Branch**: `002-runpod-serverless` (planned; current worktree remains on feature 001 until owner commits) | **Date**: 2026-08-12 | **Spec**: `specs/002-runpod-serverless/spec.md`
**Input**: Approved feature specification from `specs/002-runpod-serverless/spec.md`

## Summary

Add an optional provider-neutral remote execution path to the existing VPS
controller. The first adapter submits asynchronous Runpod queue jobs, while an
S3-compatible object store carries one immutable MP3 and one authoritative JSON
result through narrowly scoped presigned URLs. SQLite persists the external job
identity before polling, restart recovery reconciles that identity before any new
submission, and the existing validator, renderers, and completion logic remain the
only route to local completion. Runpod workers scale from zero and back to zero;
the initial request policy uses a two-hour execution timeout and three-hour TTL.

## Technical Context

**Language/Version**: Python 3.11+ controller and worker; POSIX shell wrappers  
**Primary Dependencies**: Controller remains Python standard library only; worker retains WhisperX/PyTorch/pyannote and adds the Runpod worker SDK after explicit owner approval  
**Storage**: Existing SQLite and immutable VPS files; temporary S3-compatible object storage for one-attempt input/result transport  
**Testing**: `unittest`, fake HTTP/provider/object-store adapters, existing transcript fixtures, owner-run Runpod acceptance  
**Target Platform**: Persistent Linux VPS controller; Runpod queue-based Serverless CUDA worker  
**Project Type**: Owner-operated CLI plus disposable GPU container  
**Performance Goals**: Expected substantially faster than real time; two-hour execution ceiling and three-hour total TTL; zero active workers when idle  
**Constraints**: One active remote job by default; no VPS credential on worker; no duplicate paid submission while outcome is indeterminate; provider status may expire after 30 minutes but the separately stored result object remains recoverable until local verification and cleanup  
**Scale/Scope**: One owner, individual MP3 jobs, one provider implementation, one worker maximum

## Constitution Check

*GATE: Passed before research and rechecked after design.*

- **Working path**: `run-next` claims one job, uploads the MP3 to transient object
  storage, submits Runpod, polls, retrieves JSON, validates/renders locally, deletes
  transfer objects, and completes the job. Fake adapters prove this without rental.
- **Data safety**: Original VPS audio remains immutable. Object keys are digest and
  attempt qualified. Local completion still requires the existing transcript
  validator, atomic derivative publication, and collision-safe source relocation.
- **Credential boundary**: The VPS retains Runpod and object-store credentials.
  The worker receives only expiring GET/PUT URLs and its model-read token, never a
  credential granting VPS or bucket-wide access.
- **Simple design**: Reuse `Config`, SQLite transactions, claims, transcript
  validation, renderers, and completion. Add small provider and object-store
  modules rather than a broker, web service, or orchestration platform.
- **Testing**: Focused tests cover state mapping, uncertain submission, restart
  reconciliation, cancellation races, explicit indeterminate resolution, URL
  signing/scope, cleanup, and duplicate prevention. Real GPU behavior stays an
  owner-run acceptance check.
- **Proportionate validation**: Validate documented Runpod limits, one real job,
  zero-idle scale-down, transfer cleanup, and credential hygiene. No production
  monitoring or multi-provider failover is introduced.

## Provider Capability Verification

Runpod's current official documentation states that queue-job
`executionTimeout` and `ttl` each support up to seven days. Endpoint settings
default to zero active workers and a five-second idle timeout. Asynchronous `/run`
results remain available for 30 minutes after completion. Therefore the required
7,200,000 ms execution timeout and 10,800,000 ms TTL are supported. The quickstart
requires recording endpoint/API evidence before acceptance.

Sources:

- https://docs.runpod.io/serverless/endpoints/send-requests
- https://docs.runpod.io/serverless/endpoints/endpoint-configurations

## Project Structure

### Documentation

```text
specs/002-runpod-serverless/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   ├── provider.md
│   └── runpod-job.schema.json
└── tasks.md
```

### Source Code

```text
field_transcriber/
├── cli.py                 # mode selection, cancel, resolve-remote
├── config.py              # provider/object-store/time-limit settings
├── db.py                  # additive remote-execution schema
├── jobs.py                # local claims and completion remain authoritative
├── orchestrator.py        # dispatch to SSH or serverless orchestration
├── remote.py              # provider-neutral contracts and reconciliation
├── runpod_provider.py     # Runpod HTTP adapter
└── object_store.py        # S3-compatible SigV4 transport and presigning

worker/
├── transcribe.py          # unchanged core operation
├── serverless.py          # thin Runpod handler and URL transfer
├── requirements.txt       # add approved Runpod SDK pin
└── Dockerfile             # serverless command mode

tests/
├── test_config.py
├── test_db.py
├── test_cli.py
├── test_remote.py
├── test_runpod_provider.py
├── test_object_store.py
├── test_serverless_worker.py
└── test_orchestrator.py
```

**Structure Decision**: Extend the existing packages in place. The serverless
wrapper is separate from `worker.transcribe.transcribe`, and provider-specific
HTTP/state mapping is separate from provider-neutral reconciliation.

## Design Decisions

1. **Asynchronous API, synchronous owner command by default**: `run-next` submits
   `/run` and polls until terminal while renewing the local claim. If interrupted,
   the next invocation reconciles persisted remote executions before claiming new
   work.
2. **One remote execution row per attempt**: External identity and state are
   durable independently of provider response retention. An attempt cannot have
   two external identities.
3. **Uncertain submission is indeterminate**: If acceptance may have occurred but
   no ID is known, automatic resubmission is forbidden. `resolve-remote` records an
   explicit owner decision after the configured deadline.
4. **S3-compatible transient transport**: The VPS signs requests with standard
   library HMAC/SHA-256. The worker receives only presigned object GET/PUT URLs.
5. **Polling only**: Webhooks are deferred. This avoids an inbound VPS endpoint and
   keeps restart recovery identical to normal operation.
6. **Additive SQLite migration**: New tables are created idempotently; existing
   recording, job, and attempt rows and checks are not rebuilt.
7. **Dependency gate**: The Runpod worker SDK is necessary to host a queue handler,
   but modifying `worker/requirements.txt` requires explicit owner approval. No
   package is installed by the implementation workflow.
8. **Result-first reconciliation**: Recovery first probes the known result object.
   A digest-matching canonical result is authoritative success even when Runpod
   status expired or is unavailable. `indeterminate` is used only when neither
   object evidence nor provider status establishes the outcome.
9. **Active remote work reclaims locally**: Reconciliation of `queued` or `running`
   work atomically replaces the stale local claim token, extends the lease, and
   associates the new token with the same attempt before expired-claim recovery.
10. **Opportunistic cleanup**: `run-next` deletes due retained objects and retries
    `cleanup_failed` records before reconciliation. The explicit cleanup command
    remains available for owner inspection and forced retries.

## Post-Design Constitution Recheck

Passed. The design adds one necessary worker dependency (approval-gated), no
controller dependency, no inbound web service, and no persistent external data
authority. Original-audio, transcript, retry, and credential guarantees are
preserved and made testable at the new boundaries.
