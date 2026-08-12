# Plan Review

## Verdict

CHANGES_REQUIRED

## Critical

None. No planned step alters an original recording, grants the worker a route back to the VPS, or reverses a verified completion.

## Important

1. **The controller is declared standard-library-only but is required to validate against a JSON Schema document.**
   - Artifact: `plan.md` Technical Context ("VPS controller uses Python standard library only") and Design → Worker protocol ("validates it against the transcript contract"); `research.md` → VPS controller dependency policy; `contracts/transcript.schema.json` (draft 2020-12).
   - Issue: Python's standard library has no JSON Schema validator, so "validate against the contract" cannot be implemented under the stated dependency policy. The plan does not say whether the schema is executable or documentary. Verified environment facts: the owner's designated interpreter `/home/assela/python/.venv/bin/python` is Python **3.12.3** and does have `jsonschema 4.26.0`, but that is a third-party package on the laptop only — the VPS environment is unstated, and `AGENTS.md` forbids installing dependencies without owner approval.
   - Consequence: Implementation will either silently add an undeclared VPS dependency (breaking the dependency policy and possibly the VPS deploy), or hand-write checks that drift from the published schema, weakening the FR-011/SC-003 completion gate that the whole design rests on.
   - Correction: State explicitly which applies — hand-written structural validation with the schema kept as documentation, or `jsonschema` as an approved controller dependency with the exact install command reported for owner approval — and make `contracts/` and the deploy step consistent with that choice.

2. **Claim expiry cannot be renewed during the one step that actually takes the longest.**
   - Artifact: `plan.md` Design → Job lifecycle and recovery ("The controller renews the lease between long orchestration steps"); `data-model.md` Job (`claim_expires_at`) and State transitions ("claim expiry → failed"); spec FR-018.
   - Issue: `run-next` is a single blocking process whose dominant step is the remote transcription run, which can last from many minutes to hours for a field recording. Renewal only "between" steps means the lease is never renewed while that step runs. The plan gives no expiry duration and no relationship between the expiry and the worst-case worker run.
   - Consequence: A second controller invocation, or the same controller's own startup recovery, can classify a healthy in-flight run as an expired claim and move the job to `failed`. The expected-current-state predicate then correctly refuses the original process's completion, so no state is corrupted — but a paid GPU run is discarded and the recording is reprocessed, which is precisely the cost this feature is trying to avoid.
   - Correction: Specify how the lease survives the blocking worker step (background heartbeat renewal, or an expiry sized to the worst-case run plus margin, made configurable), and state what the controller does when it finds its own claim expired mid-run.

3. **Result validation does not implement the spec's non-empty-content completion gate.**
   - Artifact: `contracts/transcript.schema.json` (`segments` has no `minItems`; `segment.speaker` is nullable); `plan.md` Design → Worker protocol; spec Data Integrity ("all three required result files exist on the VPS and pass basic format and non-empty-content checks") and Edge Cases ("A recording contains silence, wind, walking noise...").
   - Issue: The plan treats schema conformance as the validation step, but the schema accepts a transcript with zero segments, and the plan never defines what "non-empty content" means for the rendered Markdown and SRT. The legitimate silent/near-silent recording case therefore has no defined outcome.
   - Consequence: Implementers must guess. A zero-segment result either completes with empty derivatives (violating the spec's non-empty gate and SC-003) or fails permanently on a recording that genuinely contains no speech, with no way to close it out.
   - Correction: Define the content checks the controller applies beyond schema conformance (for example a minimum viable segment/word condition), and state the intended handling of a valid but speechless transcript — complete with a recorded note, or fail with an actionable message.

## Later

1. `plan.md` Technical Context and `quickstart.md` prerequisites specify Python 3.11, but the owner's designated project interpreter is Python 3.12.3 (verified) and `quickstart.md` step 1 invokes exactly that interpreter. Align the stated version, or state that 3.11+ is the requirement.
2. `contracts/cli.md` `quarantine` moves a failed job's input to `failed/` and marks the Recording `quarantined`, while `retry` rejects only on job state. Nothing prevents retrying a quarantined recording, which would reprocess an input the owner declared non-retryable. This inherits the spec-level gap noted in round 2 of the spec review (no terminal disposition); a one-line rule in `retry` would close it.
3. `plan.md` Project Structure adds `scripts/deploy-vps.sh`, `test-local.sh`, and `test-worker.sh` to the existing `scripts/` directory, which currently holds only the SDD orchestration script `ai_flow.py`. Harmless, but worth confirming the mixing of workflow tooling and project deployment scripts is intended.
4. `plan.md` and `data-model.md` describe recovery reconciliation after an interruption between transcript publication, job completion, and source relocation, but only in one sentence. Task generation should turn that reconciliation into an explicit, tested step rather than an assumption.
5. Cleanup is invoked after completion and recorded on the Attempt (`cleanup_status`), but no command re-attempts cleanup for a worker that was unreachable at the time. Acceptable for disposable workers; note it so it is a conscious omission.

## Ignore

- Worker stack (pinned WhisperX with faster-whisper backend, `large-v3`, CUDA float16, VAD, forced alignment, pyannote `speaker-diarization-community-1`) matches `AGENTS.md` and the spec, with alternatives documented in `research.md`.
- The read-only Hugging Face token injected into the container is an external-service credential, not a route back to the VPS; it is runtime-injected rather than baked into the image, consistent with spec Credential and Data Safety and constitution IV. The gated-model acceptance prerequisite is correctly surfaced in `quickstart.md`.
- Transfer directions (laptop pushes to VPS; VPS pushes input and pulls results; worker never connects outward) satisfy the credential boundary and resolve the round-2 spec `Later` item about FR-011's unnamed initiator.
- Upload staging, digest verification, and atomic publication implement spec FR-017 faithfully; discovery scans only `incoming/`.
- The closed state machine in `data-model.md` matches the spec's transition set exactly, with single-transaction transitions guarded by expected-current-state predicates.
- No daemon, API server, Redis, Celery, or ORM is introduced; SQLite plus files plus rsync/SSH/SCP is proportionate to one operator and one active job.
- Injecting the external-command runner is the right seam for testing failure paths without a GPU, and the `unittest`-based strategy matches constitution III.
- No database migration concern exists — this is a first-time schema created by `init`.
- Nullable `speaker` and nullable word timing/confidence in the schema correctly preserve uncertainty rather than inventing values, per the spec edge case.
- The plan drops `idea.txt`'s `systemd/` and `/data/...` paths in favour of manual `run-next` and the owner-mandated `/home/assela/field-transcriber/` layout; this follows the spec Input and reduces scope appropriately.

## Evidence

Artifacts inspected:

- `specs/001-field-transcription-pipeline/plan.md`
- `specs/001-field-transcription-pipeline/research.md`
- `specs/001-field-transcription-pipeline/data-model.md`
- `specs/001-field-transcription-pipeline/quickstart.md`
- `specs/001-field-transcription-pipeline/contracts/cli.md`
- `specs/001-field-transcription-pipeline/contracts/transcript.schema.json`
- `specs/001-field-transcription-pipeline/spec.md` (approved round 2) and `checklists/requirements.md`
- `.specify/memory/constitution.md`, `AGENTS.md`, `idea.txt`

Commands run:

- `python3 scripts/ai_flow.py claim` → `{"iteration": 1, "result": "claimed", "stage": "plan"}`
- `/home/assela/python/.venv/bin/python -V` → `Python 3.12.3`
- `/home/assela/python/.venv/bin/python -c "import jsonschema; print(jsonschema.__version__)"` → `4.26.0`

Not validated: no implementation exists yet, so no build, test, or deployment check was applicable. Worker/GPU, Docker, and VPS environments were not inspected; findings about them rest on the plan text alone.

No specification, plan, task, implementation, or documentation file was modified.
