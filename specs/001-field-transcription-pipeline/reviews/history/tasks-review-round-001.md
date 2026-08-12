# Tasks Review

## Verdict

CHANGES_REQUIRED

## Critical

None. No task performs a destructive operation, installs dependencies, deploys, commits, or edits the permanent source recording, and T038 correctly gates the rented-GPU run behind owner authorization.

## Important

1. **No task covers SC-005, and the repository is already in a state where the first commit can embed field data.**
   - Artifact: `tasks.md` Phase 1 (T001-T004) and Phase 6 (T035-T037); spec `SC-005` ("Inspection of the repository and worker image finds zero embedded credentials, original field recordings, or transcripts"); spec Credential and Data Safety.
   - Issue: Every other success criterion maps to a task, but SC-005 maps to none. Verified repository state: `.gitignore` contains exactly one line, `.ai-flow/`, and `git status` shows an untracked field recording `260811_0111.MP3` at the repository root. The tasks then introduce further ignorable artifacts — the runtime `config.env` referenced by `quickstart.md`, the SQLite database, transcript outputs, and local test scratch directories — while T002/T003 only create `*.example.env` files.
   - Consequence: A routine `git add -A` during implementation commits a field recording and potentially a populated `config.env`, failing SC-005 and the constitution's data-safety principle in a way that is awkward to undo once pushed. This is the single highest-value preventable failure in the list.
   - Correction: Add a Setup-phase task that extends `.gitignore` to exclude field audio, transcripts, runtime config (`config.env`, `*.env` other than examples), and database/state files; and add an explicit SC-005 verification step to T037 (repository inspection) and T029/T038 (worker image inspection).

2. **T005's "fail-first" configuration tests are scheduled after the configuration implementation they are supposed to drive.**
   - Artifact: `tasks.md` T002 (Phase 1, "Create safe configuration loading and validation in `field_transcriber/config.py`") versus T005 (Phase 2, "Write fail-first schema initialization and configuration tests in `tests/test_db.py` and `tests/test_config.py`").
   - Issue: Configuration loading and validation is implemented in Phase 1, one phase before the test task that claims to be written fail-first against it. The database half of T005 is correctly ordered ahead of T006; the configuration half is not.
   - Consequence: The test cannot fail first, so it will be written to match whatever T002 produced. Configuration validation is where the credential boundary, path roots, and lease settings are enforced, so a test written to confirm existing behavior is materially weaker than one written to specify it.
   - Correction: Either move configuration implementation out of T002 into Phase 2 after T005, or split T005 so the configuration test precedes the configuration implementation. If configuration is deliberately treated as non-test-first (permitted by constitution III), drop the "fail-first" wording so the intent is honest.

## Later

1. T002 creates `config.example.env` while T003 creates `local/config.example.env` and `vps/config.example.env`. Three example files across two tasks, and `vps/` does not appear in the approved `plan.md` Project Structure (which lists only `local/config.example.env`). Clarify which files exist where.
2. T010 introduces `field_transcriber/commands.py`, which is absent from the approved `plan.md` Project Structure although the plan's design does describe a single command-runner boundary. Harmless, but the structure and tasks should agree.
3. Spec Acceptance Scenario 1.3 and SC-004's duplicate-submission case are covered only implicitly, by "rediscovery" in T011 (`tests/test_recordings.py`) while the registration logic lands in T014 (`field_transcriber/jobs.py`). Naming the assertion — repeated publish or discovery of the same digest yields exactly one active job — would make the coverage explicit.
4. T037 records validation results into `specs/001-field-transcription-pipeline/quickstart.md`, mixing run output into a design artifact. A separate results note would keep the Spec Kit artifact stable.
5. The plan-review `Later` item about `retry` on a quarantined recording is still open; T030 tests retry and quarantine but no task states the guard rule.
6. No task re-attempts cleanup for a worker that was unreachable at completion time. Consistent with the approved plan; noted so it stays a conscious omission.

## Ignore

- Phase order (Setup → Foundational → US1 → US2 → US3 → docs/validation) matches the story priorities, and each phase's checkpoint is independently demonstrable without a GPU.
- Test-before-implementation ordering holds everywhere else: T005→T006, T008→T009, T011/T012→T013-T017, T018-T021→T022-T029, T030/T031→T032-T034.
- No task installs dependencies or deploys. T028/T029 only author the image definition and smoke guidance; T036 creates a deploy helper without running it; T037 runs the stdlib-only `unittest` suite with the owner's designated interpreter.
- T038 correctly isolates the rented-GPU, gated-model, owner-authorized acceptance run, and the Implementation Strategy tells the implementer to stop and report the exact owner action rather than weaken the check.
- Task granularity is appropriate — each names its target files and a reviewable outcome — and `[P]` markers are applied only to tasks touching disjoint files.
- No migration concern: T006 creates a first-time schema idempotently.
- Scope is bounded — no web UI, no automatic GPU provisioning, no LLM analysis, no observability stack.
- Data-safety-first ordering is respected: digest identity, atomic publication, and partial-file exclusion (T011/T013) precede any processing task.
- Secret handling is a task-level concern rather than an afterthought (T010 bounded secret-scrubbed errors, T031 stderr-bounding tests, T034 secret-safe diagnostics).
- The MVP framing (Setup + Foundation + US1, then US2 with a fake worker) prioritizes user-critical behavior over polish.

## Evidence

Artifacts inspected:

- `specs/001-field-transcription-pipeline/tasks.md`
- Approved `spec.md` and `plan.md`, plus `data-model.md`, `research.md`, `quickstart.md`, `contracts/cli.md`, `contracts/transcript.schema.json`
- `.gitignore`, repository root state
- `.specify/memory/constitution.md`, `AGENTS.md`

Commands run:

- `python3 scripts/ai_flow.py claim` → `{"iteration": 1, "result": "claimed", "stage": "tasks"}`
- `cat .gitignore` → single entry `.ai-flow/`
- `git status --short` → untracked `260811_0111.MP3` at repository root

Not validated: no implementation exists, so no test or build command was applicable. Worker, GPU, and VPS environments were not inspected.

No specification, plan, task, implementation, or documentation file was modified.
