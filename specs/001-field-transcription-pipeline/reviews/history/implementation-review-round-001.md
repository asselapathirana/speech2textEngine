# Implementation Review

## Verdict

CHANGES_REQUIRED

## Critical

1. **Completion overwrites an existing processed original with the same filename.**
   `field_transcriber/jobs.py:110` builds `destination = config.processed_dir /
   claim.recording.original_name` and `jobs.py:115-116` performs
   `os.replace(current_path, destination)` with no collision guard, even though
   `quarantine_job` (`jobs.py:201-202`) does guard its destination.
   Consequence: an Olympus recorder reuses sequential filenames, so a later
   recording named `260811_0111.mp3` destroys the earlier, already-completed
   original. Reproduced in a temporary directory: after the second completion the
   first original's bytes were unrecoverable, and because `recordings.current_path`
   is `UNIQUE`, the subsequent `UPDATE` raised
   `sqlite3.IntegrityError: UNIQUE constraint failed: recordings.current_path`,
   rolling the transaction back and leaving job 2 in `processing` with a live claim
   token and a `current_path` pointing at a file that no longer exists. This
   violates the constitution's immutable-original rule, the Data Integrity &
   Lifecycle rule that the original "remains byte-for-byte unchanged ... during any
   later relocation", and FR-013. It is irreversible field-data loss.
   Correction: make the processed destination collision-safe (for example
   digest-qualified) or refuse relocation when the destination exists with a
   different digest, and move the source only after the completion transaction has
   committed.

2. **`run-next` deadlocks against a real worker once it produces ~64 KB of output.**
   `field_transcriber/commands.py:44` starts the remote command with
   `stdout=subprocess.PIPE, stderr=subprocess.PIPE`, and
   `field_transcriber/orchestrator.py:62-67` polls `running.poll()` without ever
   draining those pipes. When the OS pipe buffer fills, the child blocks on write
   and `poll()` never returns. Reproduced with a stand-in child writing ~1 MB to
   stderr: the loop was still spinning after 15 s with the child blocked.
   Consequence: WhisperX model downloads, tqdm progress bars, and pyannote warnings
   far exceed the buffer, so the primary path (`upload -> run-next -> transcript`)
   hangs indefinitely on the rented GPU. The heartbeat keeps renewing the claim, so
   lease expiry never rescues it and rental time is burned until the operator
   intervenes. Correction: redirect the child's stdout/stderr to temporary files (or
   drain them on background threads) and read a bounded tail for diagnostics.

3. **The detected language is discarded from the authoritative JSON.**
   `worker/transcribe.py:56-58` rebinds `result = whisperx.align(result["segments"],
   ...)`; `align` receives only the segment list and returns only aligned segments,
   so the `language` key produced by `model.transcribe` (used correctly one line
   earlier at `transcribe.py:57`) is lost. `normalize_result`
   (`worker/transcribe.py:35`) then falls back to `raw.get("language", "und")` and
   reads `language_probability`, which the WhisperX transcribe result does not
   expose. Consequence: `language.code` is `"und"` and `language.confidence` is
   `null` on every real run, so the authoritative transcript never carries the
   detected language required by FR-010, and the validator accepts it silently
   because `"und"` is a non-empty string. `tests/test_worker_transcribe.py:10` masks
   this by feeding `normalize_result` a raw dict that still contains `"language"`,
   which the real call site cannot produce. Correction: capture the language code and
   any probability from the transcription result before rebinding and pass them into
   `normalize_result` explicitly.
   Verification limit: `whisperx` is not installed and installation is not
   authorized, so this was established from the call structure and the existing use
   of `result["language"]`, not by executing WhisperX.

## Important

1. **Non-`DomainError` failures escape orchestration error handling.**
   `field_transcriber/orchestrator.py:91-93` catches only `DomainError`. The
   `sqlite3.IntegrityError` demonstrated in Critical 1 propagated out of `run_next`
   without `fail_claim` running, leaving the job `processing` with a live token,
   `latest_error` empty, and the attempt row unfinished. Consequence: real failures
   produce no actionable error record, contradicting FR-005 and FR-012, and the job
   is only reachable through lease expiry. Correction: convert or wrap unexpected
   exceptions at the orchestration boundary so every claimed job records a failure.

2. **Completion reconciliation is missing although marked complete.**
   `plan.md:100-103` and `data-model.md:96-98` require recovery checks that
   "reconcile a safely moved source or published transcript after an interruption
   before repeating work", and T024/T020 are checked `[X]` for it, but no such logic
   exists in `field_transcriber/jobs.py` (a repository-wide search for
   reconciliation logic finds only specification text). Because the source move at
   `jobs.py:115-116` precedes the completion transaction at `jobs.py:118-129`, an
   interruption in between leaves `recordings.current_path` pointing at a file that
   has already moved to `processed/`. Consequence: `recover_expired_claims` marks the
   job failed, `retry_job` accepts it because the recording still reads `incoming`,
   and every subsequent attempt fails at `worker_upload` on a missing file — an
   unrecoverable loop that contradicts US3 acceptance scenario 3. Correction:
   implement the specified reconciliation, or reorder so the database commit
   precedes the relocation.

3. **Transcripts are published before claim ownership is re-verified.**
   `field_transcriber/orchestrator.py:79` calls `publish_transcripts` before
   `complete_claim` performs its ownership check, and
   `field_transcriber/renderers.py:44-62` unconditionally replaces
   `transcripts/<digest>/<stem>.{json,md,srt}`. Consequence: a controller that has
   lost its claim still overwrites files that a second controller may already have
   verified and completed, which is exactly the silent replacement of a valid
   completed result that FR-013 forbids. Correction: verify ownership immediately
   before publication, or publish into the staging directory and move into
   `transcripts/` inside the completion transaction.

4. **The CLI does not match `contracts/cli.md`.**
   `field_transcriber/cli.py:19` makes `--config` `required=True`, but the contract
   writes it as optional (`cli.md:6`) and omits it from every command example
   (`cli.md:28`, `cli.md:48`, `cli.md:66`), so a user following the contract gets
   exit 2. `cli.py:31-32` implements `status` with no `--job` or `--recording`
   selector although `cli.md:57` documents both. Consequence: the documented
   operator interface is not the delivered one, and `status` output cannot be
   narrowed as specified. Correction: add the documented selectors and either give
   `--config` a default or correct the contract.

5. **Several behaviours claimed by checked tasks have no test.**
   T020 claims renewal, token-loss, and cleanup-status tests, but
   `tests/test_orchestrator.py:52-54` uses a fake whose `poll()` returns `0`
   immediately, so the heartbeat loop, the claim-loss termination branch
   (`orchestrator.py:64-67`), and cleanup-status recording are never exercised. T031
   claims cleanup-failure and retry-to-completion tests, but
   `tests/test_failure_recovery.py` contains only an upload-failure test and a
   `scrub` unit test. T012 claims a repeated-upload test, but
   `tests/test_upload_script.py` has a single command-construction test.
   Consequence: SC-004's coverage claim is overstated, and both Critical findings
   above sit in code the suite never executes. Correction: add the missing tests or
   reopen the tasks.

## Later

1. `field_transcriber/orchestrator.py:54` passes the Hugging Face token inside the
   remote command string, so it is visible in the worker's process list and any SSH
   command logging. Diagnostics are scrubbed, so this is exposure on the worker
   only. Passing it through the SSH environment or a short-lived remote file would
   narrow it.
2. `field_transcriber/transcript.py:60` rejects any segment starting before the
   previous segment ended. If real alignment ever emits an overlap, the attempt
   fails deterministically and retry cannot clear it. Worth revisiting during the
   deferred GPU run.
3. `field_transcriber/recordings.py:62` accepts any non-empty `*.mp3` without an
   audio-format check, so non-audio input is only rejected after GPU time is spent.
4. `worker/Dockerfile` ships no model cache and the container runs `--rm`, so every
   disposable run re-downloads `large-v3`, the alignment model, and the diarization
   model. This is a rental-cost item, not a correctness one.
5. `field_transcriber/db.py:60-65` returns connections that several callers use as
   bare context managers (`jobs.py:28`, `jobs.py:111`, `jobs.py:192`), which commits
   but never closes them. Harmless in short-lived CLI processes.
6. `field_transcriber/jobs.py:107` accepts any non-empty `.json`/`.md`/`.srt` file
   in the transcript directory rather than the specific published paths, and the
   Markdown/SRT content checks in `cli.md:117-118` are not enforced.

## Ignore

- Repository credential and field-data hygiene meets SC-005 for the tracked tree:
  no audio, database, transcript, or non-example env file is tracked, and a secret
  pattern scan of tracked files outside specifications and tests returned nothing.
  `.gitignore` and `.dockerignore` cover the relevant classes.
- User Story 1 is implemented and tested as specified: staged upload verification,
  atomic publication, digest identity across renames, filename-collision rejection,
  partial-file exclusion, and idempotent discovery.
- `scripts/deploy-vps.sh` is gated behind an explicit opt-in, excludes field data
  and runtime configuration from the copy, and rsync's exclusions also protect those
  paths from `--delete-delay`.
- `scripts/test-worker.sh` is gated behind an explicit build opt-in and performs the
  image credential and field-data inspection it claims.
- `local/upload.sh` validates the basename before interpolating it into the remote
  shell command, so the uploader's SSH invocation is not injectable.
- `specs/002-runpod-serverless/` is untracked, is a new feature specification rather
  than part of this implementation, and was not reviewed here.
- The T038 deferral is recorded honestly in `docs/gpu-acceptance.md` as
  "DEFERRED, NOT PASSED" with an explicit release boundary. The owner authorization
  it asserts cannot be verified from the repository and is accepted as stated. Note
  that Critical 2 and Critical 3 are precisely the class of defect that the deferred
  real-worker run would have surfaced.

## Evidence

Artifacts inspected: `specs/001-field-transcription-pipeline/spec.md`, `plan.md`,
`tasks.md`, `data-model.md`, `contracts/cli.md`; `field_transcriber/` (`cli.py`,
`commands.py`, `config.py`, `db.py`, `jobs.py`, `models.py`, `orchestrator.py`,
`recordings.py`, `renderers.py`, `transcript.py`); `worker/` (`Dockerfile`,
`entrypoint.sh`, `requirements.txt`, `transcribe.py`); `local/upload.sh`;
`scripts/deploy-vps.sh`, `scripts/test-local.sh`, `scripts/test-worker.sh`;
`tests/` (all modules); `.gitignore`, `.dockerignore`; `docs/gpu-acceptance.md`; and
the uncommitted `quickstart.md`/`tasks.md` changes.

Commands run:

- `git status --short`, `git branch --show-current`, `git diff --stat main...HEAD`,
  `git diff HEAD -- specs/001-field-transcription-pipeline/`: implementation is
  commit `41d94f6` against baseline `4c5a3ba`, plus uncommitted `quickstart.md` and
  `tasks.md` edits and untracked `docs/gpu-acceptance.md` and
  `specs/002-runpod-serverless/`.
- `/home/assela/python/.venv/bin/python -B -m unittest discover -s tests`:
  32 tests, OK. Matches the record in `quickstart.md`.
- `sh -n` on all five shell scripts: passed.
- `/home/assela/python/.venv/bin/python -B -m compileall -q field_transcriber worker`:
  passed.
- `git ls-files` filtered for audio/database/transcript/env extensions and
  `git grep` for private-key, `hf_`, and inline-password patterns: no hits outside
  specifications, tests, and the scanner regex in `scripts/test-worker.sh`.
- Focused probe in a temporary directory using the project's own modules
  (`initialize`, `discover`, `claim_next`, `complete_claim`) with two different
  recordings sharing one filename: reproduced Critical 1, including the destroyed
  original, the `UNIQUE constraint failed: recordings.current_path` rollback, and
  the job left in `processing`.
- Focused probe using `field_transcriber.commands.CommandRunner.start` with the
  orchestrator's poll-loop shape against a child writing ~1 MB to stderr:
  reproduced Critical 2; the loop was still running after 15 s.

Commands skipped:

- Docker image build and any worker smoke run (`scripts/test-worker.sh`): requires
  image and dependency downloads plus a GPU host, and is owner-gated.
- Importing or executing WhisperX to confirm Critical 3 directly: `whisperx` is not
  installed and installing dependencies is not permitted, so that finding rests on
  the call structure rather than execution.
- The rented-GPU end-to-end acceptance run: owner-deferred to feature
  `002-runpod-serverless` and outside a reviewer's authority.

Readiness: not ready for merge. Three Critical findings affect irreplaceable source
audio, the primary processing path, and a required field of the authoritative
transcript, and two of the three lie in code the current suite never executes.
