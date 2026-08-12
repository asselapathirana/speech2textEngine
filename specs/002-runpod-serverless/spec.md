# Feature Specification: Disposable Serverless GPU Execution

**Feature Branch**: Not yet created  
**Created**: 2026-08-12  
**Status**: Draft  
**Input**: Replace manual SSH-managed GPU execution with automatically scaled Runpod Serverless jobs while keeping the transcription pipeline portable, preserving the VPS as controller and authority, and ensuring GPU compute stops promptly after each job. A hard one-hour execution timeout must not cause valid long recordings to fail.

## User Scenarios & Testing

### User Story 1 - Process on Disposable Compute (Priority: P1)

As the owner, I can submit a pending recording from the VPS and have suitable GPU
compute start only when needed, produce the transcript, and stop automatically
after the work finishes.

**Why this priority**: It removes manual GPU rental, connection, and shutdown while
preserving the core value of the existing transcription pipeline.

**Independent Test**: Submit one representative recording while no worker is
active, verify that processing starts without manual provisioning, all outputs
arrive and pass existing validation, and no active worker remains after the
configured idle period.

**Acceptance Scenarios**:

1. **Given** a pending recording and no active GPU worker, **When** the owner runs the next job, **Then** the system requests processing and records the external job identity without requiring a worker hostname or SSH session.
2. **Given** an accepted remote job, **When** processing completes, **Then** the VPS retrieves or receives the authoritative result, validates and publishes the required transcript outputs, and marks the local job complete.
3. **Given** the remote job has finished and no further work is queued, **When** the idle period expires, **Then** billable worker compute stops automatically without owner action.

---

### User Story 2 - Recover Without Wasting Compute (Priority: P1)

As the owner, I can diagnose, retry, or cancel remote processing without losing the
original recording, duplicating completed work, or leaving compute running
unnecessarily.

**Why this priority**: Network failures, remote queue delays, and worker failures
must not create hidden cost or inconsistent local state.

**Independent Test**: Simulate interruption after submission and after remote
completion, restart the controller, and verify that it reconciles the existing
remote job rather than submitting an unnecessary duplicate.

**Acceptance Scenarios**:

1. **Given** the controller stops after remote submission, **When** it restarts, **Then** it uses the persisted external job identity to recover status and continue safely.
2. **Given** a remote job fails, expires, is cancelled, or exceeds its execution limit, **When** the controller reconciles it, **Then** the local attempt records an actionable failure and remains eligible for the existing retry workflow.
3. **Given** the owner cancels a processing job, **When** cancellation succeeds or the job is already terminal, **Then** the local state reflects the outcome and no new remote job is silently submitted.

---

### User Story 3 - Retain Provider Portability (Priority: P2)

As the owner, I can replace the remote GPU provider later without rewriting audio
processing, transcript validation, rendering, or the local job lifecycle.

**Why this priority**: Serverless operation is useful, but the transcription tool
should not become inseparable from one provider's request and status conventions.

**Independent Test**: Exercise the controller with a fake provider implementing the
documented job contract and verify submission, status reconciliation,
cancellation, result handling, and failure mapping without importing a Runpod
client in core transcription modules.

**Acceptance Scenarios**:

1. **Given** a provider-specific adapter, **When** the controller submits or checks a job, **Then** core orchestration uses a provider-neutral request, status, and result contract.
2. **Given** a new provider implementation in the future, **When** it satisfies that contract, **Then** existing transcription, transcript rendering, and local lifecycle behavior require no provider-specific changes.
3. **Given** provider-specific response fields or failures, **When** they cross into the controller, **Then** they are mapped to the shared job states and bounded diagnostics rather than leaking through the application.

### Edge Cases

- Remote capacity is unavailable and a submitted job remains queued.
- The remote job is accepted but its identifier is not persisted locally.
- Submission times out after the provider accepted the job, making success uncertain.
- A status request is rate-limited, temporarily unavailable, or returns an unknown state.
- The controller claim expires while the remote job continues running.
- Processing completes, but the result expires before the VPS retrieves it.
- The result transfer grant expires during input download or output upload.
- A webhook is duplicated, delayed, forged, or arrives after polling already completed the job.
- The provider retries a handler and two executions attempt to publish results for the same recording.
- A one-hour recording requires more than one hour of processing because of cold start, model loading, alignment, diarization, or reduced GPU performance.
- Cancellation races with successful completion.
- Remote cleanup or scale-down is delayed after the transcript has been safely published.
- The provider is unavailable while locally queued recordings remain safe on the VPS.

## Requirements

### Functional Requirements

- **FR-001**: The VPS MUST remain the authority for recording identity, job state, retries, transcript validation, final publication, and completion.
- **FR-002**: The system MUST support a remote execution mode in which a pending local job can be submitted without an owner-provided worker hostname or manual GPU provisioning.
- **FR-003**: Remote execution MUST start worker compute on demand and MUST allow it to return to zero active workers after work finishes.
- **FR-004**: The controller MUST persist the provider name, external job identifier, submission time, last known remote state, and latest reconciliation time before treating submission as durable.
- **FR-005**: The controller MUST reconcile submitted remote jobs after restart and MUST NOT create a replacement job while an earlier submission may still be active or successfully completed.
- **FR-006**: The provider integration MUST support submission, status retrieval, cancellation, and conversion of provider outcomes into a closed provider-neutral state set.
- **FR-007**: The provider-neutral remote state set MUST distinguish at least queued, running, succeeded, failed, cancelled, expired, and indeterminate outcomes.
- **FR-008**: The remote worker MUST reuse the existing provider-neutral transcription operation and transcript schema; provider request handling MUST remain a wrapper around that operation.
- **FR-009**: The remote worker MUST receive access only to the single recording and result destination required for its current job.
- **FR-010**: File access granted to a remote worker MUST be narrowly scoped, time-limited, revocable where practical, and insufficient to enumerate or retrieve unrelated recordings or transcripts.
- **FR-011**: The remote worker MUST publish an authoritative JSON transcript or a result manifest that enables the VPS to retrieve that transcript; the VPS MUST validate JSON and generate Markdown and SRT locally before completion.
- **FR-012**: Remote success MUST NOT mark the local job complete until the VPS has obtained, validated, and atomically published all required local outputs.
- **FR-013**: Duplicate remote execution, repeated status responses, and repeated completion notifications MUST be idempotent and MUST NOT overwrite a valid transcript silently.
- **FR-014**: Provider credentials, transfer credentials, and model-access credentials MUST be supplied at runtime, redacted from diagnostics, and absent from committed files, container layers, transcript data, and durable provider-neutral job records.
- **FR-015**: The system MUST use asynchronous remote jobs so controller availability and ordinary request duration do not limit transcription runtime.
- **FR-016**: Execution and total-lifetime limits MUST be configurable independently. The initial safe configuration MUST permit at least two hours of active processing and at least three hours from submission through queueing and result retrieval.
- **FR-017**: The owner MUST be able to lower or raise those limits after measuring representative recordings without changing application code.
- **FR-018**: The controller MUST retrieve successful remote results promptly and MUST treat result-retention expiry as a retryable, actionable failure rather than completion.
- **FR-019**: Transient provider and network errors MUST use bounded retry with backoff; retries MUST respect remote-job identity and MUST not become duplicate submissions.
- **FR-020**: The owner MUST be able to select the existing SSH worker mode or the serverless provider mode through configuration during migration and fallback.
- **FR-021**: Core recording, transcript, rendering, and local job-state modules MUST NOT depend directly on provider-specific request or response structures.
- **FR-022**: The initial provider adapter MUST support the selected Runpod serverless endpoint while exposing only the shared provider contract to core orchestration.
- **FR-023**: The configured endpoint MUST allow zero always-active workers and MUST cap concurrency at one worker unless the owner explicitly changes the limit.
- **FR-024**: Remote job diagnostics MUST retain enough bounded information to distinguish queue delay, processing failure, timeout, cancellation, transfer failure, result expiry, and provider unavailability.
- **FR-025**: Webhook completion MAY supplement status polling, but successful processing and local completion MUST remain recoverable when webhook delivery fails.
- **FR-026**: The owner MUST be able to cancel an active remote job through the existing command-line tool. If cancellation races with completion, the controller MUST reconcile authoritative remote status and accept a valid completed result rather than overwrite it with a cancelled outcome.
- **FR-027**: An indeterminate remote job MUST remain blocked from automatic resubmission. After a configurable reconciliation deadline, the controller MUST expose an owner command that records an explicit abandon-and-retry or continue-waiting decision; no elapsed time alone may authorize a potentially duplicate paid submission.
- **FR-028**: Original audio and generated results MUST transit temporary object storage outside the VPS under the control of the selected transfer-storage provider. The system MUST delete successful-attempt objects after verified local publication and MUST delete failed-attempt objects after a documented, bounded diagnostic retention period.
- **FR-029**: Before planning is approved, the selected endpoint MUST be verified to support at least the required two-hour execution and three-hour total-lifetime limits. If it cannot, planning MUST select another endpoint type or provider that does; splitting recordings is not an implicit fallback and requires a separate specification because it changes transcript alignment and diarization semantics.

### Data Integrity & Lifecycle Rules

- Original MP3 files remain immutable and permanently controlled by the VPS.
- A local processing attempt may reference at most one active or indeterminate
  external job. A replacement submission requires evidence that the earlier job
  cannot still produce a result, or explicit owner intervention.
- External job identity and state are coordination metadata, not the authority for
  local completion. Existing transcript validation and publication rules remain
  authoritative.
- A successful remote transcript may be accepted more than once, but publication
  must be idempotent and tied to the expected recording digest.
- Failed, cancelled, expired, and indeterminate outcomes retain sufficient local
  state for diagnosis and safe retry.
- Temporary transfer objects and grants are not permanent transcript storage and
  must be deleted after the VPS verifies local publication. Failed-attempt objects
  may remain only for a documented, bounded diagnostic retention period and must
  then be deleted even if the job is not retried.

### Input, Output & Compatibility Boundaries

- The controller sends a provider-neutral job request containing recording
  identity, bounded processing options, and narrowly scoped transfer references.
- Original recordings and authoritative JSON results cross from the VPS into
  temporary object storage operated by the selected transfer-storage provider;
  this store is a transient transport boundary, not an archive or authority.
- The provider adapter translates the shared request and provider responses without
  changing the transcription schema or local state model semantics.
- The remote worker verifies that downloaded input matches the expected recording
  digest before processing.
- The remote result identifies the recording digest and schema version and is
  rejected if either conflicts with the local job.
- Unknown provider states, malformed responses, incompatible transcript schemas,
  and missing result objects become explicit non-success outcomes.
- Existing SSH execution remains compatible during migration; this feature does
  not require simultaneous execution through more than one provider.

### Credential and Data Safety

- The remote worker must not receive SSH credentials or another credential that
  grants general access back to the VPS.
- Transfer authorization must be limited to one expected input and the minimum
  output location for one attempt, with expiry longer than the expected execution
  window plus a bounded transfer margin.
- The VPS holds the provider API credential and does not transmit it to the worker.
- Model-access credentials available to the worker must have only the access needed
  to load the selected models and must not appear in returned results or logs.
- Completion notifications must be authenticated or treated only as a prompt to
  query authoritative provider status; notification content alone cannot complete
  a local job.

### Performance and Cost Expectations

- A one-hour hard execution cutoff is not considered safe for an approximately
  one-hour recording because startup, model loading, alignment, and diarization add
  variable overhead. The initial active-processing allowance is at least two hours.
- The first representative remote run must record queue duration, startup duration,
  processing duration, result-transfer duration, selected GPU class, and observed
  worker scale-down delay.
- With no queued or running work, the normal steady state is zero active workers.
- The owner can impose a one-worker concurrency cap and finite execution/lifetime
  limits to bound accidental spend.
- No formal transcription speed target is imposed until measurements from the
  representative recording are available.

### Validation Strategy

- Use fake-provider tests for state mapping, uncertain submission, polling,
  backoff, cancellation races, restart recovery, duplicate completion, result
  expiry, and prevention of duplicate remote submissions.
- Test provider-neutral transcription independently from the serverless request
  wrapper.
- Test transfer grants for object scope and expiry without exposing real secrets.
- Run one owner-observed end-to-end acceptance job with zero workers initially,
  then verify valid local outputs and automatic return to zero active workers.
- Verify through provider configuration or API inspection that the effective
  execution limit is at least two hours and total job lifetime is at least three
  hours, independent of how quickly the representative recording completes.
- Inspect configuration, logs, returned results, and image history for leaked
  provider, transfer, VPS, or model credentials.
- Inspect the transfer store after successful cleanup and after the bounded failed
  attempt retention period to verify that no field audio or transcript objects remain.

### Key Entities

- **Remote Execution**: Provider-neutral record connecting one local attempt to a provider, external job identity, remote state, submission and reconciliation timestamps, and bounded diagnostics.
- **Provider Adapter**: Boundary that submits, inspects, and cancels remote jobs while translating provider-specific states into the shared contract.
- **Transfer Grant**: Short-lived authorization scoped to one input or result location for one processing attempt.
- **Result Manifest**: Small provider response identifying the source digest, transcript schema, output location or inline result, and available execution measurements.
- **Remote Worker Invocation**: Potentially repeated execution of the serverless wrapper for one external job; it must remain safe under retries.

## Assumptions

- Runpod queue-based serverless execution is the first provider implementation.
- The configured endpoint has zero always-active workers, a maximum of one worker,
  and a short idle scale-down interval.
- Runpod's selected queue-based endpoint is assumed to support a configurable
  execution limit of at least two hours and total job lifetime of at least three
  hours. Planning must verify this current provider capability before relying on it.
- Asynchronous status polling is the required completion mechanism; a webhook is an
  optional latency optimization.
- The chosen transfer mechanism can issue per-object, short-lived read and write
  authorization without giving the worker general VPS access.
- One recording is processed per remote job.
- The existing transcript schema, validation, renderers, recording lifecycle, and
  owner-operated CLI remain authoritative.
- The initial two-hour execution allowance and three-hour total lifetime are safety
  defaults, not promises that every recording will finish within those periods.
- Indeterminate submissions require an explicit owner decision after bounded
  reconciliation attempts; the controller never infers permission for a duplicate
  paid submission from elapsed time alone.

## Out of Scope

- Supporting multiple simultaneous GPU providers or automatic cross-provider failover.
- Running more than one transcription job concurrently by default.
- Replacing the VPS, SQLite queue, existing transcript schema, or upload workflow.
- A web dashboard, user accounts, production monitoring platform, or billing dashboard.
- Real-time transcription, streaming audio ingestion, or interactive low-latency inference.
- Long-term storage of original recordings or authoritative transcripts at the compute provider.
- Automatic retry that can incur a second remote charge while the status of the first submission remains indeterminate.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Starting with zero active workers, one representative recording reaches valid local JSON, Markdown, and SRT outputs through a single owner command and returns to zero active workers without manual provisioning or shutdown.
- **SC-002**: In restart tests after submission, during processing, and after remote success, 100% of attempts reconcile the persisted external job rather than creating a duplicate while its outcome remains possible.
- **SC-003**: Tests for every shared remote state produce one defined local outcome and preserve the original recording in all cases.
- **SC-004**: A fake provider can replace the initial provider adapter in controller tests without changes to transcription, transcript validation, rendering, recording lifecycle, or local job-state modules.
- **SC-005**: Inspection of committed files, worker image history, durable job records, logs, returned results, and the temporary transfer store after required cleanup finds zero provider API keys, VPS access credentials, unrestricted transfer credentials, residual field audio, or residual transcript objects.
- **SC-006**: Provider configuration or API evidence confirms an effective execution limit of at least two hours and total lifetime of at least three hours; the representative acceptance run records selected GPU class plus queue, startup, processing, transfer, and scale-down timing.
- **SC-007**: For a successful remote job, local completion occurs only after 100% of required outputs pass existing identity, schema, format, and non-empty-content checks.
- **SC-008**: When no work is queued or running, the endpoint maintains zero active workers after the configured idle interval in the owner-observed acceptance run.
