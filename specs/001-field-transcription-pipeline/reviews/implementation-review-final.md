# Implementation Review

## Verdict

APPROVED

## Critical

None.

## Important

None.

## Later

1. `field_transcriber/cli.py:11` still imports `recover_expired_claims`, which the
   `run-next` handler no longer calls. Harmless dead import; worth removing so the
   ownership of recovery ordering stays obvious.
2. `field_transcriber/jobs.py:191-194` catches only `DomainError` around
   `complete_claim`, so a non-domain failure during reconciliation (an `OSError`
   from a permission or filesystem problem, for example) would still escape
   `run_next` at `orchestrator.py:40`, outside the guarded region. The realistic
   cases are covered now that the destination collision is gone, so this is a
   robustness note rather than a live defect.
3. `field_transcriber/commands.py:33-38` closes both diagnostic temporary files
   inside `wait()`, so a second `wait()` would raise on a closed file, and the
   claim-loss branch at `orchestrator.py:65-67` calls `terminate()` without ever
   calling `wait()`, leaving that child unreaped and its temporary files released
   only at garbage collection. Neither is reachable through current call paths.
4. Lifecycle destinations now use two different disambiguators —
   `processed/<sha256>-<name>` (`jobs.py:137-138`) and
   `failed/<recording-id>-<name>` (`jobs.py:271`). Both are correct and both are
   documented at `data-model.md:91-92`, but one convention would be easier to
   reason about.
5. Carried forward from earlier rounds and still open, all previously accepted as
   non-blocking: the Hugging Face token travels in the remote command string
   (`orchestrator.py:54`), so it is visible in the worker's process list;
   `transcript.py:60` rejects any segment starting before the previous one ended;
   `recordings.py:62` accepts any non-empty `*.mp3` without an audio-format check,
   so non-audio input is only rejected after GPU time is spent; the worker image
   ships no model cache, so every `--rm` run re-downloads the models;
   `db.py:60` connections used as bare context managers are never closed; and
   `jobs.py:127` accepts any non-empty `.json`/`.md`/`.srt` in the transcript
   directory rather than the specific published paths.
6. The rented-GPU acceptance run and worker image inspection remain the open
   release risk. `docs/gpu-acceptance.md` records this correctly as
   "DEFERRED, NOT PASSED" with an explicit boundary, and nothing in this review
   substitutes for it. Two of the three round-1 Critical findings lived in code
   that only a real worker run exercises, which is a fair measure of what that
   check is still worth.

## Ignore

All findings from rounds 1 and 2 are resolved. I verified each against the revised
code rather than reading the diff alone:

- Round-2 Critical 1 (reconciliation unreachable through the CLI):
  `cli.py:76` no longer calls `recover_expired_claims` before `run_next`, so
  `run_next` owns the recover/reconcile ordering. Re-running the probe that
  demonstrated the defect, the same interrupted-completion state now ends
  `('complete', None)` through `field_transcriber.cli.main(["run-next"])` instead of
  the previous `('failed', 'claim_expired')` dead end.
- Round-2 Important 1 (partial publication wedging the controller):
  `jobs.py:191-194` now records a reconciliation failure and continues. Probed with
  one job interrupted after only `.json` and `.md` were published and a second
  healthy recording pending: the first became
  `('failed', 'completion_reconciliation')` on both the job and the attempt row,
  and the same invocation went on to claim and complete the second job. Previously
  both calls raised and no job could be claimed.
- Round-2 Important 2 (quarantine collision): `jobs.py:271` now derives
  `failed/<recording-id>-<name>`. Probed with two different recordings both named
  `a.mp3`: both quarantined successfully to `1-a.mp3` and `3-a.mp3` with their
  distinct contents intact.
- Round-2 Later 1: `data-model.md:91-92` now documents both new destination shapes.
- Round-1 Critical 1 (same-filename source overwrite): verified in round 2 by
  re-running the probe — both originals survive under distinct digest-qualified
  paths.
- Round-1 Critical 2 (worker-output deadlock): verified in round 2 — the child that
  previously hung on a full stderr pipe finishes in 0.2 s.
- Round-1 Critical 3 (detected language discarded): `worker/transcribe.py:56-58`
  captures the language before `align` rebinds the result, and
  `test_transcribe_preserves_language_before_alignment` exercises the real
  `transcribe` against stubbed modules.
- Round-1 Important 1, 3, 4, 5: unexpected exceptions record a
  `controller_unexpected` failure; ownership is re-verified before publication;
  the CLI matches `contracts/cli.md`; and the missing tests for the heartbeat loop,
  claim-loss termination, cleanup failure, retry-to-completion, and repeated upload
  all exist.
- Repository hygiene still meets SC-005: no tracked audio, database, transcript, or
  runtime configuration file, and no secret patterns outside specifications, tests,
  and the scanner's own regex.
- The `quickstart.md` validation record matches what I measured (48 tests).
- `specs/002-runpod-serverless/` remains untracked and out of scope for this review.

## Evidence

Artifacts inspected: the working-tree diff against commit `41d94f6` for
`field_transcriber/cli.py`, `commands.py`, `jobs.py`, `orchestrator.py`, and
`worker/transcribe.py`; the test changes across `tests/test_cli.py`,
`test_failure_recovery.py`, `test_jobs.py`, `test_orchestrator.py`,
`test_upload_script.py`, `test_worker_transcribe.py`; and the updated
`specs/001-field-transcription-pipeline/data-model.md`, `quickstart.md`, and
`tasks.md`.

Commands run:

- `git status --short`, `git diff HEAD -- field_transcriber/ worker/`, and targeted
  diffs of the specification documents: revision is uncommitted against `41d94f6`.
- `/home/assela/python/.venv/bin/python -B -m unittest discover -s tests`:
  48 tests, OK. Matches the count recorded in `quickstart.md`.
- `sh -n` on all five shell scripts: passed.
- `/home/assela/python/.venv/bin/python -B -m compileall -q field_transcriber worker`:
  passed.
- `git diff --check`: passed.
- `git ls-files` filtered for audio, database, transcript, and runtime config
  extensions, and `git grep` for private-key and `hf_` token patterns: no hits.
- Round-2 probe re-run in temporary directories: interrupted completion driven
  through `field_transcriber.cli.main(["--config", ..., "run-next"])` now reconciles
  to `complete`.
- New probe combining a partially published transcript directory with a second
  healthy pending recording, then quarantining two same-named recordings:
  confirmed per-job reconciliation diagnosis, continued progress within the same
  invocation, and collision-free quarantine destinations.

Commands skipped:

- Docker image build and worker smoke run: owner-gated, requires image and
  dependency downloads and a GPU host.
- Executing WhisperX end to end: `whisperx` is not installed and installing
  dependencies is not permitted. The language fix is verified by the stubbed-module
  test and by reading the call sequence, not by a real transcription.
- The rented-GPU outdoor-audio acceptance run: owner-deferred to feature
  `002-runpod-serverless`.

Readiness: ready for merge as a locally validated implementation. No Critical or
Important findings remain, every previously reported defect was re-verified as
fixed against running code, and the outstanding items are the deferred GPU
acceptance plus the non-blocking notes above. Per `docs/gpu-acceptance.md`, the
pipeline should not be treated as field-ready until that run is completed and
recorded.
