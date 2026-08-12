# Implementation Review

## Verdict

CHANGES_REQUIRED

## Critical

1. **The new reconciliation never runs through the `run-next` command, so the
   round-1 unrecoverable-job defect is still live.**
   `field_transcriber/orchestrator.py:40` calls
   `reconcile_interrupted_completions` before `recover_expired_claims`, which is
   correct. But `field_transcriber/cli.py:76` still calls
   `recover_expired_claims(config)` *before* `run_next(config)`, and
   `reconcile_interrupted_completions` selects only rows with
   `j.status='processing'` (`jobs.py:178`). The CLI's pre-call flips the expired
   row to `failed` first, so reconciliation finds nothing.
   Reproduced from the real entry point: a job whose transcripts were published and
   whose source had already moved to `processed/` was reported
   `{"result": "no_job"}` and left as `('failed', 'claim_expired')`; calling
   `reconcile_interrupted_completions` directly on the identical state instead
   produced `('complete', None)`. The follow-on state is unrecoverable — `retry`
   is accepted because `recordings.status` is still `incoming`, and the next run
   dies at `worker_upload | No such file or directory` because
   `recordings.current_path` points at an `incoming/` file that no longer exists.
   Every further retry repeats that failure.
   Consequence: a recording that was fully transcribed is reported as failed and
   can never be cleared without hand-editing the database, contradicting FR-013 and
   US3 acceptance scenario 3. The new tests pass only because they call `run_next`
   directly and bypass `cli.py`.
   Correction: remove the redundant `recover_expired_claims` call from the
   `run-next` handler so `run_next` owns the recover/reconcile ordering, and add a
   test that drives this path through `field_transcriber.cli.main`.

## Important

1. **A partially published transcript directory wedges `run-next` permanently.**
   `field_transcriber/orchestrator.py:40` calls
   `reconcile_interrupted_completions` outside the `try` block that would call
   `fail_claim`, and `jobs.py:187-191` skips a row only when the transcript
   directory is absent — any other `complete_claim` failure propagates.
   `renderers.py:54-66` publishes the three files one at a time, so an interruption
   between them leaves a directory holding, say, only `.json` and `.md`. Reproduced
   by invoking `run_next` twice on that state: both calls raised
   `completion | required transcript outputs are missing or empty`, and no job was
   claimed either time. Consequence: once Critical 1 is fixed and reconciliation
   actually runs, one incomplete directory stops the controller from claiming any
   job, on every invocation, until someone deletes files by hand. Correction: treat
   a reconciliation failure as a per-job diagnosis (record it and continue, or move
   the reconciliation inside the guarded region) rather than letting it abort
   `run_next`.

2. **The collision fix was applied to `processed/` but not to `failed/`.**
   `jobs.py:141-142` now derives a digest-qualified processed destination, but
   `jobs.py:267-269` still uses `config.failed_dir / row["original_name"]` and
   raises `quarantine destination already exists` when a second recording shares the
   filename. Consequence: with the recorder's recycled filenames, the `quarantine`
   command documented at `contracts/cli.md:84-91` becomes permanently unusable for
   that job, and the owner has no supported way to set the input aside.
   Correction: apply the same digest-qualified naming used by `processed_path` to
   the quarantine destination.

## Later

1. `data-model.md:91` still documents `incoming/<name> --verified job completion-->
   processed/<name>`, but completions now write `processed/<sha256>-<name>`. The
   naming change is the right fix; the data model should record it so an operator
   looking for a file finds the documented shape.
2. `commands.py:33-38` closes both diagnostic temporary files inside `wait()`, so a
   second `wait()` raises on a closed file, and the claim-loss branch at
   `orchestrator.py:65-67` calls `terminate()` without ever calling `wait()`, so
   that child is never reaped and its temporary files are released only at garbage
   collection. Neither is reachable today, but a reaping `terminate()` would be
   sturdier.
3. Carried forward from round 1 and still open, all previously accepted as
   non-blocking: the Hugging Face token travels in the remote command string
   (`orchestrator.py:54`); `transcript.py:60` rejects any segment starting before the
   previous one ended; `recordings.py:62` accepts any non-empty `*.mp3` without an
   audio-format check; the worker image ships no model cache, so every `--rm` run
   re-downloads the models; `db.py:60` connections used as bare context managers are
   never closed; and `jobs.py:127` accepts any non-empty `.json`/`.md`/`.srt` in the
   transcript directory rather than the specific published paths.

## Ignore

The three round-1 Critical findings and three of the five round-1 Important
findings are resolved, and I re-ran the probes that demonstrated them:

- Same-filename source relocation: `processed_path` (`jobs.py:137-138`) now yields
  `<sha256>-<name>`, guarded by digest checks on both source and destination
  (`jobs.py:143-156`). Re-running the round-1 probe, two different recordings both
  named `260811_0111.mp3` completed successfully and both originals survived intact
  with distinct processed paths. `test_same_filename_completions_preserve_both_originals`
  covers it.
- Worker-output deadlock: `commands.py:58-66` now redirects the child to temporary
  files and `wait()` reads a bounded tail. Re-running the round-1 probe, the child
  that previously hung on a full stderr pipe finished in 0.2 s.
  `test_running_command_does_not_block_on_large_stderr` covers it.
- Detected language: `worker/transcribe.py:56-58` captures `language` and
  `language_probability` from the transcription result before rebinding through
  `align`, and passes them explicitly. `test_transcribe_preserves_language_before_alignment`
  exercises the real `transcribe` against stubbed modules and asserts
  `{"code": "nl", "confidence": 0.87}`, which the previous test could not have caught.
- Unexpected exceptions now record a failure (`orchestrator.py:96-99`), with
  `test_unexpected_failure_records_attempt` asserting the `controller_unexpected`
  job and attempt rows.
- Ownership is re-verified before publication (`orchestrator.py:80`), with
  `test_lost_claim_prevents_transcript_publication` asserting `publish_transcripts`
  is not called.
- The CLI now matches `contracts/cli.md`: `--config` defaults to `config.env` and
  `status` accepts mutually exclusive `--job`/`--recording`, both tested.
- The remaining round-1 test gaps are closed: heartbeat renewal, claim-loss
  termination with cleanup status, cleanup failure without reverting completion,
  retry-to-completion, and repeated upload all have tests.
- Repository hygiene still meets SC-005: no tracked audio, database, transcript, or
  runtime configuration file.
- `specs/002-runpod-serverless/` remains untracked and out of scope for this review.
- The T038 deferral is unchanged and still recorded honestly as
  "DEFERRED, NOT PASSED" in `docs/gpu-acceptance.md`.

## Evidence

Artifacts inspected: the working-tree diff against commit `41d94f6` for
`field_transcriber/cli.py`, `commands.py`, `jobs.py`, `orchestrator.py`,
`worker/transcribe.py`, and `tests/test_cli.py`, `test_failure_recovery.py`,
`test_orchestrator.py`, `test_upload_script.py`, `test_worker_transcribe.py`; the
updated `specs/001-field-transcription-pipeline/quickstart.md` and `tasks.md`;
`specs/001-field-transcription-pipeline/data-model.md` and `contracts/cli.md` for
conformance; `field_transcriber/renderers.py` and `recordings.py` as unchanged
context.

Commands run:

- `git status --short` and `git diff HEAD -- field_transcriber/ worker/ tests/`:
  revision is uncommitted against `41d94f6`.
- `/home/assela/python/.venv/bin/python -B -m unittest discover -s tests`:
  45 tests, OK. Matches the count recorded in `quickstart.md`.
- `sh -n` on all five shell scripts: passed.
- `/home/assela/python/.venv/bin/python -B -m compileall -q field_transcriber worker`:
  passed.
- `git ls-files` filtered for audio, database, transcript, and runtime config
  extensions: no hits.
- Round-1 Critical probes re-run against the revised code in temporary directories:
  same-filename completion now preserves both originals; the poll-loop probe that
  previously hung finished in 0.2 s.
- New probe driving `field_transcriber.cli.main(["--config", ..., "run-next"])` on an
  interrupted-completion state, compared against a direct
  `reconcile_interrupted_completions` call on the identical state: demonstrated
  Critical 1, including the subsequent `retry` acceptance and the repeating
  `worker_upload | No such file or directory` dead end.
- New probe invoking `run_next` twice on a partially published transcript
  directory: demonstrated Important 1, with both calls raising
  `completion | required transcript outputs are missing or empty`.

Commands skipped:

- Docker image build and worker smoke run: owner-gated, requires image and
  dependency downloads and a GPU host.
- Executing WhisperX to confirm the language fix end to end: `whisperx` is not
  installed and installing dependencies is not permitted. The fix is verified by
  the stubbed-module test and by reading the call sequence.
- The rented-GPU acceptance run: owner-deferred to feature `002-runpod-serverless`.

Readiness: not ready for merge. The revision genuinely fixes the three round-1
Critical findings, and I verified two of them by re-running the probes that
demonstrated them. One Critical remains because the reconciliation added for
round-1 Important 2 is bypassed by the CLI's own recovery call, leaving the same
unrecoverable job state reachable from the documented operator command; fixing that
also activates the wedge described in Important 1, so the two need to be addressed
together.
