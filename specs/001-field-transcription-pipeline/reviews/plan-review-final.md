# Plan Review

## Verdict

APPROVED

## Critical

None.

## Important

None. All three round-1 findings are resolved, and the fixes are consistent across every design artifact rather than patched in one place:

1. **Validation dependency** — `research.md` → VPS controller dependency policy now decides explicitly to keep `transcript.schema.json` as a documentary and test-fixture contract and implement matching runtime checks with the standard library, rejecting `jsonschema` with a stated rationale. `plan.md` Worker protocol and the new `contracts/cli.md` → Transcript validation contract say the same. No undeclared VPS dependency remains, so `AGENTS.md`'s no-install rule is respected.
2. **Claim lease during the blocking worker step** — the command-runner boundary now supports a pollable long-running process (`plan.md` Controller boundaries); the lease is a configurable five minutes renewed every 60 seconds during remote execution, with the renewal interval required to stay below the lease (`data-model.md` Job, State transitions). Loss of renewal or of token ownership stops result acceptance and triggers best-effort remote termination instead of finalizing (`plan.md` Job lifecycle, `contracts/cli.md` `run-next`, `research.md` → Claim renewal during remote processing). Split-brain completion is prevented by the token-guarded predicate, and a healthy paid run is no longer discarded.
3. **Non-empty-content gate** — `transcript.schema.json` now sets `segments.minItems: 1`, and `contracts/cli.md` → Transcript validation contract enumerates the completion checks (a segment with non-whitespace text, finite ordered times with `end >= start`, timed-word sanity, at least one rendered Markdown segment, at least one valid SRT cue). The silent-recording case has a defined, named outcome: retryable failure `no_speech_detected`, source retained, nothing published (`research.md` → Empty and speechless output, `data-model.md`).

Re-checked for contradictions introduced by the revision: the recovery path cannot cause two concurrent worker runs, because `run-next` moves an expired claim to `failed` rather than straight back to `pending`, and only explicit `retry` re-queues it. That remains consistent with the approved spec's closed transition set.

## Later

1. `plan.md` Technical Context, `research.md` (CUDA baseline and dependency policy), and `quickstart.md` prerequisites still state Python 3.11, while the owner's designated project interpreter is Python 3.12.3 (verified) and `quickstart.md` step 1 invokes exactly that interpreter. The controller is stdlib-only so both work; align the stated version or say "3.11+".
2. `contracts/cli.md` `quarantine` marks a Recording `quarantined` and moves its input to `failed/`, while `retry` rejects only on job state. Nothing prevents retrying a quarantined recording. This inherits the spec-level gap noted in the round-2 spec review; a one-line rule in `retry` would close it.
3. The hand-written validator "must remain behaviorally aligned" with the documentary schema. Drift is the accepted cost of the stdlib decision. Since `jsonschema 4.26.0` is already present in the owner's laptop venv, a development-only fixture test asserting the shared fixtures satisfy both the schema and the validator would cheaply pin that alignment — worth considering during task generation, not a blocker.
4. A genuinely speechless recording now fails repeatedly with `no_speech_detected` and can only be closed out through `quarantine`. Correct given the spec's completion gate; confirm the owner is content with quarantine as the closing action.
5. `plan.md` and `data-model.md` describe post-interruption reconciliation between transcript publication, job completion, and source relocation in a single sentence. Task generation should make it an explicit, tested step.
6. No command re-attempts cleanup for a worker that was unreachable at completion time; `cleanup_status` records the fact. Acceptable for disposable workers — noted so it stays a conscious omission.
7. `plan.md` Project Structure adds `deploy-vps.sh`, `test-local.sh`, and `test-worker.sh` to `scripts/`, which currently holds only the SDD orchestration script `ai_flow.py`. Harmless mixing of workflow tooling and project scripts.

## Ignore

- Worker stack (pinned WhisperX with faster-whisper backend, `large-v3`, CUDA float16, VAD, forced alignment, pyannote `speaker-diarization-community-1`) matches `AGENTS.md` and the spec, with documented alternatives.
- The read-only Hugging Face token is an external-service credential injected at container runtime, not baked into the image, and gives the worker no route back to the VPS — consistent with spec Credential and Data Safety and constitution IV.
- Transfer directions (laptop → VPS push; VPS pushes input and pulls results; worker never connects outward) enforce the credential boundary.
- Upload staging, digest verification, and atomic publication implement FR-017 faithfully; discovery scans only `incoming/`.
- The `data-model.md` state machine matches the spec's transition set exactly, with single-transaction transitions guarded by expected-current-state predicates.
- No daemon, API server, Redis, Celery, ORM, or repository abstraction is introduced; the heartbeat runs in the controller's own loop rather than a new service.
- The injected command runner remains the right seam for exercising rsync/SSH/SCP failures and lease expiry without a GPU; `unittest` strategy matches constitution III.
- No migration concern — this is a first-time schema created by `init`.
- Nullable `speaker` and nullable word timing/confidence preserve uncertainty rather than inventing values, per the spec edge case.
- Dropping `idea.txt`'s `systemd/` and `/data/...` layout in favour of manual `run-next` and the owner-mandated `/home/assela/field-transcriber/` paths follows the approved spec and reduces scope.

## Evidence

Artifacts inspected (round 2):

- `specs/001-field-transcription-pipeline/plan.md` (full re-read)
- `specs/001-field-transcription-pipeline/research.md` (dependency policy, claim renewal, empty-output sections)
- `specs/001-field-transcription-pipeline/data-model.md`
- `specs/001-field-transcription-pipeline/quickstart.md`
- `specs/001-field-transcription-pipeline/contracts/cli.md` (including the new validation contract)
- `specs/001-field-transcription-pipeline/contracts/transcript.schema.json`
- Approved `spec.md` and `.specify/memory/constitution.md`, `AGENTS.md`

Commands run:

- `python3 scripts/ai_flow.py claim` → `{"iteration": 2, "result": "claimed", "stage": "plan"}`
- `grep -n "minItems|segments|speaker" contracts/transcript.schema.json` (confirmed `minItems: 1`)
- `grep -n` across artifacts for `jsonschema`, `lease`, `heartbeat`, `retry`, `quarantine`, Python version (cross-artifact consistency)
- Round-1 environment checks retained: `/home/assela/python/.venv/bin/python -V` → `Python 3.12.3`; `jsonschema` → `4.26.0`

Not validated: no implementation exists yet, so no build, test, or deployment check applied. Worker/GPU, Docker, and VPS environments were not inspected; conclusions about them rest on the plan text.

No specification, plan, task, implementation, or documentation file was modified. The plan is ready for task generation; the `Later` items are non-blocking follow-ups.
