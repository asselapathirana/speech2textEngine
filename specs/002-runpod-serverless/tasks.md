# Tasks: Disposable Serverless GPU Execution

**Input**: Design documents from `/specs/002-runpod-serverless/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Focused automated tests precede implementation for state transitions, idempotency, signing, transfer cleanup, provider mapping, worker result handling, and CLI recovery. The real Runpod/GPU check remains owner-run because it transfers field audio and incurs provider charges.

**Organization**: Tasks are grouped by user story so each story remains independently testable. User Stories 1 and 2 share priority P1, but US1 establishes the executable path before US2 adds recovery operations.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and does not depend on an incomplete task
- **[Story]**: Maps the task to its user story
- Every task names an exact file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish configuration and the explicit dependency decision before implementation.

- [X] T001 Add an implementation-evidence section and dependency-gate outcome field to `specs/002-runpod-serverless/quickstart.md`
- [X] T002 Obtain explicit owner approval to add the Runpod worker SDK before modifying `worker/requirements.txt`
- [X] T003 [P] Add failing serverless configuration tests for mode selection, environment-variable indirection, HTTPS validation, timeout/TTL relationships, polling, retention, and one-worker defaults in `tests/test_config.py`
- [X] T004 Implement provider-neutral serverless and object-store configuration parsing without embedded secrets in `field_transcriber/config.py` and document variables in `config.example.env`
- [X] T005 After T002 approval, add the pinned Runpod worker SDK requirement in `worker/requirements.txt` without installing it

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add durable remote state and shared transfer/provider boundaries required by every story.

**Critical**: No user story implementation begins until this phase is complete.

- [X] T006 [P] Add failing additive-migration and invariant tests for remote executions and transfer objects in `tests/test_db.py`
- [X] T007 Add idempotent `remote_executions` and `transfer_objects` schema, constraints, indexes, and row conversion helpers in `field_transcriber/db.py`
- [X] T008 Add provider-neutral remote states, request/status value objects, bounded diagnostic scrubbing, and provider protocol definitions in `field_transcriber/remote.py`
- [X] T009 [P] Add failing claim-renewal tests proving an active remote attempt receives a replacement token without a new attempt in `tests/test_jobs.py`
- [X] T010 Implement atomic same-attempt claim replacement and lease renewal for active remote work in `field_transcriber/jobs.py`
- [X] T011 Add shared result identity/schema validation and local publication helpers reusable by SSH and serverless paths in `field_transcriber/orchestrator.py`, with existing SSH tests passing unchanged before and after extraction

**Checkpoint**: Durable provider-neutral state and local authority rules are ready.

---

## Phase 3: User Story 1 - Process on Disposable Compute (Priority: P1) MVP

**Goal**: Submit one pending recording to on-demand Runpod compute, transport one input and result through scoped object URLs, validate and publish outputs locally, clean transfer objects, and allow the endpoint to return to zero workers.

**Independent Test**: With fake HTTP and object storage, run one pending recording from zero worker state through upload, submission, result retrieval, local JSON/Markdown/SRT publication, transfer deletion, and completion without an SSH hostname.

### Tests for User Story 1

- [X] T012 [P] [US1] Add failing SigV4 upload/download/head/delete and one-object presigned URL tests in `tests/test_object_store.py`
- [X] T013 [P] [US1] Add failing Runpod request-schema, async submission, state-mapping, bounded-backoff, and secret-redaction tests in `tests/test_runpod_provider.py`
- [X] T014 [P] [US1] Add failing worker tests with stubbed Runpod modules for request validation, digest checking, existing transcription invocation, canonical JSON upload, and bounded manifest output in `tests/test_serverless_worker.py`
- [X] T015 [P] [US1] Add failing end-to-end fake-provider tests for one-attempt submission, local output validation/publication, cleanup, and completion in `tests/test_remote.py`

### Implementation for User Story 1

- [X] T016 [US1] Implement standard-library S3-compatible SigV4 requests, scoped presigning, object probing, transfer verification, and idempotent deletion in `field_transcriber/object_store.py`
- [X] T017 [US1] Implement the Runpod `/run`, `/status/{id}`, and `/cancel/{id}` HTTP adapter with normalized states and bounded retries in `field_transcriber/runpod_provider.py`
- [X] T018 [US1] Implement remote execution creation, input upload, durable external identity, polling, result retrieval, local validation/publication, and cleanup in `field_transcriber/remote.py`
- [X] T019 [US1] Dispatch `run-next` between existing SSH mode and serverless mode while preserving existing completion semantics in `field_transcriber/orchestrator.py`
- [X] T020 [US1] Add the thin Runpod queue handler that downloads one MP3, verifies identity, calls `worker.transcribe.transcribe`, and uploads canonical JSON in `worker/serverless.py`, confining the deferred or guarded Runpod SDK import to the handler entry point so tests run without installation
- [X] T021 [US1] Add a serverless worker command path without baking runtime credentials into the image in `worker/Dockerfile` and `worker/entrypoint.sh`
- [X] T022 [US1] Expose serverless `run-next` JSON fields without credentials or signed URLs in `field_transcriber/cli.py`
- [X] T023 [US1] Run the US1 fake-provider flow and existing SSH regression tests from `tests/test_remote.py`, `tests/test_orchestrator.py`, `tests/test_worker_transcribe.py`, and `tests/test_cli.py`

**Checkpoint**: The provider-backed MVP processes and publishes one recording while the VPS remains authoritative.

---

## Phase 4: User Story 2 - Recover Without Wasting Compute (Priority: P1)

**Goal**: Reconcile interrupted, failed, cancelled, expired, and uncertain work without duplicate paid submissions or loss of original recordings.

**Independent Test**: Interrupt fake remote work after submission and after completion, restart through the CLI, and prove the same remote execution is reconciled result-first; then exercise cancellation, explicit indeterminate decisions, retention cleanup, and retry eligibility.

### Tests for User Story 2

- [X] T024 [P] [US2] Add failing restart tests for result-first recovery, status-retention expiry, same-attempt claim renewal, duplicate-submission prevention, and invalid result objects falling through to provider status without aborting `run-next` in `tests/test_remote.py`
- [X] T025 [P] [US2] Add failing cancellation-race, terminal failure mapping, result expiry, and explicit wait/abandon-retry tests in `tests/test_failure_recovery.py`
- [X] T026 [P] [US2] Add failing due-retention and cleanup-failure retry tests in `tests/test_object_store.py`
- [X] T027 [P] [US2] Add failing `field_transcriber.cli.main` journey tests for restart reconciliation, result-first recovery, `cancel`, `resolve-remote`, opportunistic cleanup, and `cleanup-transfers` in `tests/test_cli.py`

### Implementation for User Story 2

- [X] T028 [US2] Implement result-object-first reconciliation before provider status and ordinary expired-claim recovery in `field_transcriber/remote.py`
- [X] T029 [US2] Implement queued/running same-attempt reclamation, terminal failure mapping, and indeterminate blocking in `field_transcriber/remote.py`
- [X] T030 [US2] Implement cancellation with authoritative result precedence and no implicit resubmission in `field_transcriber/remote.py`
- [X] T031 [US2] Implement deadline-gated `wait` and `abandon-retry` owner decisions with durable audit fields in `field_transcriber/remote.py`
- [X] T032 [US2] Implement successful cleanup, failed-attempt retention, `cleanup_failed` retries, and opportunistic due cleanup in `field_transcriber/object_store.py`
- [X] T033 [US2] Add `cancel --job`, `resolve-remote --job --decision`, and `cleanup-transfers` command handling in `field_transcriber/cli.py`
- [X] T034 [US2] Order startup reconciliation and transfer cleanup before expired-claim recovery or new claims in `field_transcriber/orchestrator.py`
- [X] T035 [US2] Run restart, cancellation, indeterminate-resolution, cleanup, and existing local failure-recovery tests from `tests/test_remote.py`, `tests/test_failure_recovery.py`, `tests/test_object_store.py`, and `tests/test_cli.py`

**Checkpoint**: Interrupted remote work is restartable, owner-resolvable, and protected from duplicate submission.

---

## Phase 5: User Story 3 - Retain Provider Portability (Priority: P2)

**Goal**: Prove core orchestration depends only on the shared provider contract and contains no Runpod-specific request or response logic.

**Independent Test**: Replace Runpod with a fake provider and exercise submission, polling, cancellation, success, failure, expiry, malformed states, and result handling without importing the Runpod adapter in recording, transcript, rendering, or job modules.

### Tests for User Story 3

- [X] T036 [P] [US3] Add provider-contract conformance tests covering all normalized states and uncertain submission in `tests/test_remote.py`
- [X] T037 [P] [US3] Add import-boundary tests preventing Runpod dependencies in core recording, transcript, rendering, and job modules in `tests/test_orchestrator.py`

### Implementation for User Story 3

- [X] T038 [US3] Refine provider injection and shared request/status interfaces so reconciliation accepts any conforming adapter in `field_transcriber/remote.py`
- [X] T039 [US3] Isolate all Runpod payload fields, URLs, status names, and HTTP diagnostics inside `field_transcriber/runpod_provider.py`
- [X] T040 [US3] Run fake-provider conformance and import-boundary tests from `tests/test_remote.py` and `tests/test_orchestrator.py`

**Checkpoint**: The Runpod adapter is replaceable without changes to core transcription or local lifecycle modules.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Complete operator documentation, security checks, and full local validation.

- [X] T041 [P] Document serverless configuration, migration fallback to SSH, commands, timeout tuning, and failure recovery in `README.md` and `docs/architecture.md`
- [X] T042 [P] Add an owner-run Runpod endpoint and representative GPU acceptance checklist, explicitly marked deferred until charged execution is authorized, in `docs/gpu-acceptance.md`
- [X] T043 Inspect tracked configuration, diagnostics, SQLite fixtures, worker files, and test outputs for credentials, signed URLs, or field-data leakage and record evidence in `specs/002-runpod-serverless/quickstart.md`
- [X] T044 Run `/home/assela/python/.venv/bin/python -B -m unittest discover -s tests -v` and record results or dependency-blocked gaps in `specs/002-runpod-serverless/quickstart.md`
- [X] T045 Run shell syntax checks, Python compilation with bytecode redirected outside the repository, and `git diff --check`, then record evidence in `specs/002-runpod-serverless/quickstart.md`
- [X] T046 Validate the mocked portions of `specs/002-runpod-serverless/quickstart.md` and record all owner-run provider/GPU steps as deferred, not passed, in `docs/gpu-acceptance.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately; T005 is blocked until explicit owner approval in T002.
- **Foundational (Phase 2)**: Depends on configuration behavior from T003-T004 and blocks all user stories.
- **US1 (Phase 3)**: Depends on Foundation and delivers the MVP remote execution path.
- **US2 (Phase 4)**: Depends on US1's persisted execution and transfer path, then adds recovery and owner control.
- **US3 (Phase 5)**: Depends on the shared contract and completed behavior from US1-US2, then verifies portability.
- **Polish (Phase 6)**: Depends on all selected user stories.

### User Story Dependencies

- **US1 (P1)**: First independently useful increment after Foundation.
- **US2 (P1)**: Requires the US1 remote lifecycle but is independently testable with interruption and failure scenarios.
- **US3 (P2)**: Verifies the completed lifecycle through a provider-neutral fake and import boundaries.

### Within Each User Story

- Write focused tests first and confirm the new behavior fails when practical.
- Implement storage and provider boundaries before orchestration integration.
- Preserve local transcript validation and publication as the only completion path.
- Run the story-specific tests before moving to the next phase.

### Parallel Opportunities

- T003 can proceed while T002 awaits the owner decision; T005 cannot.
- T006 and T009 target separate test files and can proceed in parallel.
- T012-T015 can be authored in parallel after Foundation.
- T024-T027 can be authored in parallel after US1.
- T036-T037 can be authored in parallel.
- T041-T042 can proceed in parallel after behavior stabilizes.

---

## Parallel Example: User Story 1

```text
Task T012: SigV4 and presigned URL tests in tests/test_object_store.py
Task T013: Runpod adapter contract tests in tests/test_runpod_provider.py
Task T014: Serverless worker wrapper tests in tests/test_serverless_worker.py
Task T015: Fake-provider lifecycle tests in tests/test_remote.py
```

## Parallel Example: User Story 2

```text
Task T024: Restart and duplicate-prevention tests in tests/test_remote.py
Task T025: Cancellation and indeterminate tests in tests/test_failure_recovery.py
Task T026: Retention cleanup tests in tests/test_object_store.py
Task T027: Owner CLI journey tests in tests/test_cli.py
```

---

## Implementation Strategy

### MVP First

1. Complete Setup, including explicit approval before changing `worker/requirements.txt`.
2. Complete Foundational schema, contracts, and claim renewal.
3. Complete US1 with fake provider and object-store checks.
4. Stop and validate local outputs, cleanup, SSH compatibility, and secret exclusion.
5. Do not run a charged provider acceptance test without separate owner authorization.

### Incremental Delivery

1. **Foundation**: Durable state and safe configuration.
2. **US1**: Disposable compute processing path.
3. **US2**: Restart, cancellation, uncertainty, and cleanup controls.
4. **US3**: Provider replacement proof.
5. **Acceptance**: Owner-authorized real Runpod run and zero-worker evidence.

## Notes

- No task installs Python or system packages.
- T002 is a hard owner-approval gate required by the constitution and plan.
- Signed URLs and secrets must never be persisted or included in CLI JSON.
- The representative GPU run remains deferred until the owner separately authorizes provider charges and external audio transfer.
