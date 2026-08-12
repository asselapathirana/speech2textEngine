# Feature Specification: Field Audio Transcription Pipeline

**Feature Branch**: `main`  
**Created**: 2026-08-11  
**Status**: Draft  
**Input**: Build a pragmatic end-to-end pipeline that uploads Olympus WS-852 MP3 recordings from the owner's laptop to a VPS, processes them on a temporary GPU worker, and returns timestamped, speaker-diarized transcripts. Passwordless SSH to the VPS is already available. Project code and field files must live in separate subdirectories below `/home/assela` on the VPS.

## User Scenarios & Testing

### User Story 1 - Upload and Register a Recording (Priority: P1)

As the owner, I can transfer an original field recording from the laptop to permanent storage on the VPS and register it for processing without altering the recording.

**Why this priority**: Safe, resumable ingestion is the prerequisite for all later processing and protects the irreplaceable source material.

**Independent Test**: Interrupt and resume the upload of a sample MP3, then verify that the VPS copy matches the laptop copy and that exactly one pending job represents the recording.

**Acceptance Scenarios**:

1. **Given** a supported MP3 on the laptop and passwordless SSH access, **When** the owner starts an upload, **Then** the file remains in a staging location until its size and content digest match the source, after which it appears atomically below `/home/assela/field-transcriber/files/incoming/` and becomes available for processing.
2. **Given** an upload interrupted before completion, **When** discovery runs or the owner repeats the upload, **Then** the partial file is ignored by discovery, transfer resumes without requiring a complete restart, and only the verified final file becomes eligible for registration.
3. **Given** the same completed recording is submitted again, **When** jobs are discovered or registered, **Then** the system does not create a second active job or overwrite prior transcript results silently.

---

### User Story 2 - Produce and Retrieve a Transcript (Priority: P1)

As the owner, I can ask the VPS to process a pending recording on a temporary GPU worker and receive a structured transcript plus readable and subtitle versions on the VPS.

**Why this priority**: This is the core user value and completes the minimum end-to-end workflow.

**Independent Test**: Process one representative multi-speaker MP3 through a disposable worker and verify the three required outputs, their essential content, and their successful return to permanent VPS storage.

**Acceptance Scenarios**:

1. **Given** a pending recording and a reachable compatible GPU worker, **When** processing runs, **Then** the recording is transcribed, word timing is aligned, speakers are diarized, and JSON, Markdown, and SRT outputs are returned to the VPS.
2. **Given** all required outputs have been transferred and verified, **When** the job is finalized, **Then** it is marked complete and temporary copies on the worker are removed.
3. **Given** output transfer is incomplete or invalid, **When** finalization is attempted, **Then** the job is not marked complete and remains recoverable.

---

### User Story 3 - Diagnose and Retry Failure (Priority: P2)

As the owner, I can see why a recording failed and retry it without losing the original audio or creating inconsistent job state.

**Why this priority**: Temporary workers and network transfers can fail. Recovery prevents repeated manual reconstruction and wasted GPU rental time.

**Independent Test**: Force a worker or transfer failure, verify the stored error and attempt record, restore the dependency, and retry the same job to completion.

**Acceptance Scenarios**:

1. **Given** a job fails during transfer or processing, **When** the controller records the failure, **Then** the original remains unchanged and the job records its state, attempt count, timestamps, and actionable error information.
2. **Given** a failed or interrupted job, **When** the owner retries it, **Then** processing resumes safely or restarts cleanly without duplicate completed outputs.
3. **Given** the controller is restarted, **When** it examines prior job state, **Then** completed jobs remain complete and interrupted jobs can be recovered or retried.

### Edge Cases

- A source filename already exists but its content differs from the incoming file.
- An MP3 is incomplete, unreadable, empty, or not actually a supported audio file.
- Discovery runs while a resumable upload is still in progress.
- The network drops during laptop-to-VPS upload, VPS-to-worker copy, or result return.
- The GPU worker is unreachable, lacks adequate GPU support or disk space, or exits partway through processing.
- Only some output files return, or an output is empty or malformed.
- A recording contains silence, wind, walking noise, distant speech, overlapping speech, one speaker, or speakers who cannot be distinguished reliably.
- Language detection or diarization confidence is weak. Output must preserve uncertainty rather than invent certainty.
- Two controller invocations attempt to claim the same pending job.
- Cleanup is requested after a failure. Permanent source audio and verified VPS results must never be treated as worker-temporary data.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST accept original Olympus WS-852 recordings in MP3 format at 128 kbps without routine normalization, denoising, or conversion before transcription.
- **FR-002**: The laptop-to-VPS upload MUST be resumable and MUST allow verification that the completed VPS file matches the source.
- **FR-003**: The VPS MUST store project code below `/home/assela/field-transcriber/code/` and field data below `/home/assela/field-transcriber/files/`.
- **FR-004**: The field-data area MUST provide separate locations for incoming recordings, processed recordings, failed-job material, transcripts, and controller state.
- **FR-005**: The system MUST maintain one durable job record per source recording, including current status, attempt count, relevant timestamps, and the latest error.
- **FR-006**: The VPS MUST select and claim pending jobs so concurrent controller activity cannot process the same job simultaneously.
- **FR-007**: The VPS MUST initiate transfers to and execution on a temporary GPU worker.
- **FR-008**: The worker MUST transcribe with the required large multilingual model, voice-activity detection, word-level timing, timestamp alignment, and speaker diarization using anonymous speaker identifiers where names are unknown.
- **FR-009**: For each successfully processed recording, the system MUST produce an authoritative JSON transcript, a readable speaker-labelled Markdown transcript, and an SRT subtitle file.
- **FR-010**: The authoritative JSON MUST include detected language and, where available, confidence information; each segment MUST include start time, end time, speaker identifier, and text; each word MUST include its timing information where alignment provides it.
- **FR-011**: The system MUST copy results to the VPS and verify the required files before marking a job complete.
- **FR-012**: The system MUST preserve failed jobs and actionable error details for retry.
- **FR-013**: Repeated discovery, upload, controller execution, or retry MUST not corrupt state, alter original audio, or silently replace a valid completed result.
- **FR-014**: After verified result transfer, the system MUST remove the recording and generated results from the disposable worker. Failed cleanup MUST be reported without invalidating already verified VPS results.
- **FR-015**: Configuration MUST allow the VPS host, remote paths, worker host, connection settings, and credentials to vary without being committed to the repository.
- **FR-016**: Optional LLM analysis, if added later, MUST remain separate from transcription outputs and MUST never overwrite the authoritative transcript.
- **FR-017**: Uploads MUST remain outside `incoming/` under `/home/assela/field-transcriber/files/uploading/` until their size and content digest agree with the laptop source. Publication into `incoming/` MUST be atomic; incomplete staged files MUST be ignored by discovery and remain available for resumed transfer or explicit cleanup.
- **FR-018**: A processing claim MUST record a unique owner token and an expiry time that is renewed while the controller is active. On startup and before claiming work, the controller MUST detect expired claims, record an interruption error, and move those jobs to the retryable `failed` state.

### Data Integrity & Lifecycle Rules

- The laptop retains its field backup, and the original VPS MP3 remains byte-for-byte unchanged after successful ingestion and during any later relocation.
- A recording is identified by stable source metadata plus a content digest. A filename collision with different content must stop for owner resolution rather than overwrite data.
- A verified recording begins in `incoming/`. On successful completion its immutable original moves to `processed/`. A retryable processing failure leaves the original in `incoming/`; if the owner explicitly declares an input non-retryable, its original moves to `failed/` with diagnostic information. The recording record retains the same identity and updates its current location, so duplicate detection searches all lifecycle locations by content digest rather than only `incoming/`.
- The complete job-state set is `pending`, `processing`, `failed`, and `complete`. Permitted transitions are `pending` to `processing`, `processing` to `complete`, `processing` to `failed`, and `failed` to `pending` for retry. An expired processing claim transitions to `failed`; no other transitions are permitted. State transitions, claims, and attempts must survive controller restarts.
- Completion is permitted only after all three required result files exist on the VPS and pass basic format and non-empty-content checks.
- The JSON transcript is authoritative. Markdown and SRT are derived views that may be regenerated from it.
- Worker files are temporary. Permanent VPS source recordings, controller state, and verified transcripts are outside worker cleanup scope.

### Input, Output & Compatibility Boundaries

- Laptop to VPS: a resumable SSH transfer carries original MP3 files into `/home/assela/field-transcriber/files/uploading/`; verification publishes a completed file atomically into `incoming/`.
- VPS to worker: the controller sends only the recording, the processing code or runnable worker package, and the minimum worker-side configuration needed for that job.
- Worker to VPS: each job returns JSON, Markdown, and SRT results for verification and permanent storage below `/home/assela/field-transcriber/files/transcripts/`.
- Unsupported, incomplete, or unreadable input must be rejected with an actionable message and without modifying an existing source or transcript.
- Speaker labels may be anonymous (`SPEAKER_01`, `SPEAKER_02`, and so forth). The system is not required to identify people by name.

### Credential and Data Safety

- Passwordless SSH from the laptop to the VPS is an available prerequisite and must not require storing a private key in this repository.
- The VPS controls the worker. A worker must not receive any private key, token, or credential that grants it access back to the VPS.
- Worker images and committed files must contain no credentials, original recordings, transcripts, or other field data.
- Only the minimum job data needed for transcription may remain on the worker, and it must be removed after successful retrieval when the worker remains reachable.

### Performance or Cost Expectations

- The processing design must be feasible on a rented NVIDIA GPU with approximately 24 GB of GPU memory, such as an RTX A5000 or equivalent.
- The owner must be able to process one representative recording end to end during a bounded rental session without manual repair of intermediate state.
- Processing time and peak GPU memory must be reported during the first real-worker acceptance run so future rental duration can be estimated. No formal throughput target is imposed initially.

### Validation Strategy

- Use focused automated tests for job creation and claiming, legal state transitions, retries, idempotency, collision handling, completion checks, and output rendering.
- Use local or mocked integration checks for interrupted transfers and worker/controller failure paths where practical.
- Before relying on the pipeline for fieldwork, run an owner-observed end-to-end test on a rented GPU with representative outdoor audio containing wind, walking, distant speakers, multiple speakers, and overlapping speech.
- Transcript quality is evaluated by reviewing timestamps, speaker changes, omissions, and obvious transcription errors on the representative recording. This initial feature does not impose a formal word-error-rate threshold.

### Key Entities

- **Recording**: An original MP3 with its source filename, content digest, size, ingestion timestamp, lifecycle disposition, and current permanent VPS location.
- **Job**: The durable processing record associated with a recording, including its closed-set state, attempts, timestamps, claim owner and expiry while processing, worker information, and latest error.
- **Transcript**: The authoritative structured result for one recording, including language, timed segments, speakers, words, and available confidence information.
- **Transcript Derivative**: A readable Markdown or SRT representation generated from the authoritative transcript.
- **Worker Run**: One attempt to process a job on a disposable GPU worker, including start/end times, outcome, and cleanup status.

## Assumptions

- The owner is the only operator; multi-user accounts, role management, and a web interface are outside scope.
- The exact VPS hostname and GPU-worker connection details will be supplied through configuration.
- `/home/assela/field-transcriber/files/` will contain `uploading/`, `incoming/`, `processed/`, `failed/`, `transcripts/`, and `state/` subdirectories.
- Recordings are processed individually in the first version. Batch discovery may enqueue several recordings, but parallel GPU processing is not required.
- Speaker names are not known in advance, and manual renaming is outside the initial feature.
- Optional LLM interpretation is outside this feature except for preserving a clean separation that permits it later.
- Automated provisioning of a rented GPU instance is outside the initial feature; the owner supplies a reachable worker host.

## Out of Scope

- A web dashboard, mobile application, multi-user access, or authentication system.
- Automatic GPU marketplace selection, rental, billing, shutdown, or provider-specific provisioning.
- Routine audio enhancement, source-file editing, speaker-name recognition, or human transcript correction tools.
- Production-scale monitoring, distributed queues, high availability, formal disaster recovery, or orchestration platforms.
- LLM-generated interpretation of transcript content.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A representative MP3 can be uploaded, processed, and returned as JSON, Markdown, and SRT in one owner-run workflow without manual editing of intermediate files or job state.
- **SC-002**: In test cases covering interruption at each transfer boundary, rerunning the workflow preserves the original recording and reaches either a clear retryable failure or one completed job without duplicate active jobs.
- **SC-003**: For every completed test job, 100% of required output files are present, non-empty, associated with the correct source recording, and verified before completion is recorded.
- **SC-004**: Automated tests cover every permitted job-state transition and the main duplicate-submission, retry, collision, and incomplete-output cases.
- **SC-005**: Inspection of the repository and worker image finds zero embedded credentials, original field recordings, or transcripts.
- **SC-006**: On the representative outdoor recording, the owner can follow the conversation using the Markdown transcript and locate passages in the audio using timestamps; known noise, overlap, or diarization limitations are visible rather than silently concealed.
- **SC-007**: After a successful representative run, no job-specific audio or transcript files remain on the worker when cleanup is possible, while the original and all verified outputs remain available on the VPS.
