# Tasks: Field Audio Transcription Pipeline

**Input**: Design documents from `specs/001-field-transcription-pipeline/`  
**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`,
`contracts/`, and `quickstart.md`

**Tests**: Focused automated tests are required by the specification for the job
state machine, claims, retries, idempotency, collisions, completion checks, and
renderers. Write these tests first where practical. GPU/audio-quality validation
remains an owner-run acceptance check.

## Phase 1: Setup

**Purpose**: Establish the dependency-free controller package, examples, and test
fixtures without installing packages or deploying anywhere.

- [X] T001 Create the controller package entry points in `field_transcriber/__init__.py` and `field_transcriber/__main__.py`
- [X] T002 Document non-secret controller and uploader variables with safe placeholder values in `config.example.env` and `local/config.example.env`
- [X] T003 [P] Exclude field audio, transcripts, runtime `config.env`/non-example environment files, SQLite/state files, model caches, and test scratch data while retaining examples in `.gitignore`
- [X] T004 [P] Create reusable transcript fixtures, including valid, malformed, and speechless results, under `tests/fixtures/`

---

## Phase 2: Foundational

**Purpose**: Implement shared persistence, domain records, command execution, and
CLI plumbing required by every user story.

- [X] T005 Write fail-first schema initialization and configuration tests in `tests/test_db.py` and `tests/test_config.py`
- [X] T006 Implement tested configuration loading/validation plus the SQLite schema, connection/transaction helpers, and idempotent initialization in `field_transcriber/config.py` and `field_transcriber/db.py`
- [X] T007 Implement Recording, Job, Attempt, command-result, and domain-error types in `field_transcriber/models.py`
- [X] T008 Write fail-first CLI exit-code and JSON-output contract tests in `tests/test_cli.py`
- [X] T009 Implement shared argument parsing, error handling, and JSON/text output in `field_transcriber/cli.py`
- [X] T010 Implement safe completed and pollable subprocess boundaries with bounded, secret-scrubbed errors in `field_transcriber/commands.py`

**Checkpoint**: The storage tree and empty database can be initialized, and CLI
errors are stable, without needing SSH or a GPU.

---

## Phase 3: User Story 1 - Upload and Register a Recording (Priority: P1)

**Goal**: Safely resume, verify, atomically publish, and register original MP3s
without duplicate jobs or altered source data.

**Independent Test**: Use temporary local/VPS directories to interrupt and resume
a sample upload, then verify digest equality, atomic publication, collision behavior,
and exactly one pending job.

### Tests

- [X] T011 [P] [US1] Write fail-first tests for digest identity, filename collisions, atomic publication, partial-file exclusion, and rediscovery in `tests/test_recordings.py`
- [X] T012 [P] [US1] Write uploader command-construction and repeated-upload tests in `tests/test_upload_script.py`

### Implementation

- [X] T013 [US1] Implement hashing, staged-file verification, atomic publication, lifecycle-path validation, and digest-based discovery in `field_transcriber/recordings.py`
- [X] T014 [US1] Implement transactional Recording and pending Job registration plus idempotent lookup in `field_transcriber/jobs.py`
- [X] T015 [US1] Add `init`, `publish-upload`, `discover`, and `status` handlers matching `contracts/cli.md` in `field_transcriber/cli.py`
- [X] T016 [US1] Implement resumable rsync upload followed by remote publication in `local/upload.sh`
- [X] T017 [US1] Add a dependency-free interrupted-upload integration check in `scripts/test-local.sh`

**Checkpoint**: User Story 1 is independently usable on laptop and VPS without a
GPU worker.

---

## Phase 4: User Story 2 - Produce and Retrieve a Transcript (Priority: P1)

**Goal**: Process one pending recording on a disposable GPU worker and publish
verified JSON, Markdown, and SRT results under VPS control.

**Independent Test**: Seed one pending recording, run the controller against a fake
worker result, and verify claim heartbeat, structural/content checks, deterministic
derivatives, atomic completion, source relocation, and worker cleanup. The owner-run
GPU check then substitutes the real worker.

### Tests

- [X] T018 [P] [US2] Write fail-first structural, timing, ordering, digest, and `no_speech_detected` validation tests in `tests/test_transcript.py`
- [X] T019 [P] [US2] Write fail-first Markdown and SRT rendering tests, including null speaker/timing behavior, in `tests/test_renderers.py`
- [X] T020 [P] [US2] Write fail-first claim, renewal, token-loss, verified-completion, relocation, reconciliation, and cleanup-status tests in `tests/test_orchestrator.py`
- [X] T021 [P] [US2] Write worker result-normalization tests with a stubbed WhisperX result in `tests/test_worker_transcribe.py`

### Implementation

- [X] T022 [US2] Implement standard-library transcript structure/content validation aligned with `contracts/transcript.schema.json` in `field_transcriber/transcript.py`
- [X] T023 [US2] Implement deterministic Markdown and SRT derivatives with atomic publication in `field_transcriber/renderers.py`
- [X] T024 [US2] Implement transactional claim, token-guarded renewal, completion, attempt metrics, and completion reconciliation in `field_transcriber/jobs.py`
- [X] T025 [US2] Implement VPS-initiated SSH/SCP orchestration, poll-loop heartbeat, result pull, validation, publication, relocation, and cleanup in `field_transcriber/orchestrator.py`
- [X] T026 [US2] Add `run-next` behavior and `no_job` output matching `contracts/cli.md` in `field_transcriber/cli.py`
- [X] T027 [US2] Implement WhisperX `large-v3` transcription, alignment, diarization, uncertainty preservation, and canonical JSON normalization in `worker/transcribe.py`
- [X] T028 [US2] Create the read-only-input worker entrypoint and pinned compatible GPU image definition in `worker/entrypoint.sh`, `worker/requirements.txt`, and `worker/Dockerfile`
- [X] T029 [US2] Create worker build/smoke guidance and an image-history/filesystem inspection that fails on embedded credentials or field data in `scripts/test-worker.sh`

**Checkpoint**: User Story 2 works end to end with a fake worker locally and has a
runnable real-worker container awaiting the owner GPU acceptance run.

---

## Phase 5: User Story 3 - Diagnose and Retry Failure (Priority: P2)

**Goal**: Preserve actionable failures, recover expired work, retry safely, and
quarantine owner-declared non-retryable input.

**Independent Test**: Force each transfer/worker failure and an expired claim,
inspect state/error/attempt data, retry once to completion, and quarantine a
separate failed input without changing either source digest.

### Tests

- [X] T030 [P] [US3] Write fail-first closed-transition, expired-claim recovery, retry, and quarantine tests in `tests/test_jobs.py`
- [X] T031 [P] [US3] Write orchestration failure-step, stderr-bounding, cleanup-failure, and retry-to-completion tests in `tests/test_failure_recovery.py`

### Implementation

- [X] T032 [US3] Implement expired-claim recovery, failure recording, guarded retry, and quarantine state/path updates in `field_transcriber/jobs.py` and `field_transcriber/recordings.py`
- [X] T033 [US3] Add `retry` and `quarantine` commands plus detailed `status` attempt output in `field_transcriber/cli.py`
- [X] T034 [US3] Complete step-specific failure handling, best-effort remote termination, and secret-safe diagnostics in `field_transcriber/orchestrator.py`

**Checkpoint**: Every permitted transition and major failure boundary is covered,
and failed jobs can be understood and recovered without manual database editing.

---

## Phase 6: Documentation and Proportionate Validation

- [X] T035 [P] Document architecture, configuration, operator flow, credential boundary, and limitations in `README.md` and `docs/architecture.md`
- [X] T036 [P] Implement a code-only VPS deployment helper that copies into `/home/assela/field-transcriber/code/` without touching field files in `scripts/deploy-vps.sh`
- [X] T037 Run `/home/assela/python/.venv/bin/python -m unittest discover -s tests -v`, shell syntax checks, and a tracked/untracked repository inspection proving no credentials, field audio, runtime databases, or transcripts are eligible for commit, then record results or skipped checks in `specs/001-field-transcription-pipeline/quickstart.md`
- [ ] T038 Perform the owner-authorized rented-GPU outdoor-audio acceptance run and worker image credential/data inspection from `specs/001-field-transcription-pipeline/quickstart.md`, then record image identifier, inspection result, wall time, peak GPU memory, cleanup outcome, and observed transcript limitations in `docs/gpu-acceptance.md`

---

## Dependencies and Execution Order

### Phase dependencies

- Setup (T001-T004) has no prerequisites.
- Foundational (T005-T010) depends on Setup and blocks all user stories.
- US1 (T011-T017) depends on Foundational.
- US2 (T018-T029) depends on Foundational; its automated independent test seeds a
  recording directly, while the real end-to-end flow uses US1.
- US3 (T030-T034) depends on Foundational and the job/orchestrator behavior from
  US2; quarantine also uses US1 lifecycle paths.
- Documentation and validation (T035-T038) follow the implemented stories. T038
  requires owner authorization, a rented worker, accepted model terms, and any
  owner-approved dependency/image downloads.

### User-story graph

```text
Setup -> Foundation -> US1 ---------------------> Final validation
                    -> US2 -> US3 --------------> Final validation
                       ^
                       └── real workflow uses US1 output
```

### Parallel opportunities

- T003 and T004 can run in parallel after T001/T002 paths are decided.
- US1 test tasks T011 and T012 touch different files and can run in parallel.
- US2 test tasks T018-T021 cover separate boundaries and can run in parallel.
- Worker implementation T027-T029 can proceed separately from controller tasks
  T022-T026 once the transcript contract is fixed.
- US3 test tasks T030 and T031 can run in parallel.
- Documentation T035 and deployment helper T036 can run in parallel.

## Parallel Examples

### User Story 1

```text
Task T011: recording publication/domain tests in tests/test_recordings.py
Task T012: uploader wrapper tests in tests/test_upload_script.py
```

### User Story 2

```text
Task T018: canonical transcript validation tests
Task T019: derivative renderer tests
Task T020: claim/completion orchestration tests
Task T021: worker normalization tests
```

### User Story 3

```text
Task T030: job-state recovery tests
Task T031: orchestration failure-boundary tests
```

## Implementation Strategy

1. Complete Setup and Foundation with no external dependencies.
2. Deliver US1 as the first independently useful increment: safe permanent upload
   and durable registration.
3. Deliver US2 first with fake-worker tests, then build the real container without
   renting or deploying a worker automatically.
4. Deliver US3 recovery behavior before relying on rented GPU processing.
5. Finish deterministic validation and documentation. Stop at T038 if GPU rental,
   model acceptance, dependency download, or deployment authority is not available;
   report the exact owner action needed rather than weakening the check.

**Suggested MVP**: Setup + Foundation + US1 (T001-T017). The smallest useful
transcription MVP additionally includes US2 through fake-worker validation
(T018-T029); real field readiness requires US3 and the owner-run T038 acceptance.
