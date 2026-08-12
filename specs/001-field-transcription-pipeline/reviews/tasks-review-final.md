# Tasks Review

## Verdict

APPROVED

## Critical

None.

## Important

None. Both round-1 findings are resolved:

1. **SC-005 coverage** — T003 (Setup) now excludes field audio, transcripts, runtime `config.env`/non-example environment files, SQLite/state files, model caches, and test scratch data from `.gitignore` while retaining examples, which closes the concrete risk that the untracked root-level `260811_0111.MP3` and a populated `config.env` get committed. Verification is now real rather than assumed: T037 adds a tracked/untracked repository inspection proving nothing sensitive is eligible for commit, T029 adds an image-history/filesystem inspection that fails on embedded credentials or field data, and T038 records the worker-image inspection result alongside the acceptance metrics.
2. **Test-first ordering for configuration** — T002 no longer implements anything; it documents non-secret example variables only. Configuration loading and validation now lands in T006, after T005's fail-first `tests/test_config.py` and `tests/test_db.py`. The "fail-first" label is now accurate for both halves of T005.

Re-checked for problems introduced by the revision: T006 now bundles configuration and database work in one task, which is larger than before but still a single reviewable unit with two named files; the `vps/config.example.env` inconsistency from round 1 disappeared with the T002 rewrite; and the parallel-opportunity notes still match the renumbered task content.

## Later

1. T010 introduces `field_transcriber/commands.py`, which is absent from the approved `plan.md` Project Structure although the plan's design describes a single command-runner boundary. Structure and tasks should agree.
2. Spec Acceptance Scenario 1.3 and SC-004's duplicate-submission case are covered only implicitly, by "rediscovery" in T011 while the registration logic lands in T014. Naming the assertion — repeated publish or discovery of the same digest yields exactly one active job — would make the coverage explicit.
3. T037 records validation results into `specs/001-field-transcription-pipeline/quickstart.md`, mixing run output into a design artifact. A separate results note would keep the Spec Kit artifact stable.
4. T032's "guarded retry" does not state whether the guard rejects a quarantined recording. This is the still-open plan-review item; one sentence in the task or `contracts/cli.md` would close it.
5. No task re-attempts cleanup for a worker unreachable at completion time. Consistent with the approved plan; noted so it stays a conscious omission.

## Ignore

- Phase order (Setup → Foundational → US1 → US2 → US3 → docs/validation) matches story priorities, and each checkpoint is independently demonstrable without a GPU.
- Test-before-implementation ordering now holds throughout: T005→T006, T008→T009, T011/T012→T013-T017, T018-T021→T022-T029, T030/T031→T032-T034.
- No task installs dependencies or deploys. T028/T029 only author the image definition and smoke/inspection guidance; T036 creates a deploy helper without running it; T037 runs the stdlib-only `unittest` suite with the owner's designated interpreter.
- T038 isolates the rented-GPU, gated-model, owner-authorized acceptance run, and the Implementation Strategy directs the implementer to stop and report the exact owner action rather than weaken the check.
- Task granularity is appropriate — each names target files and a reviewable outcome — and `[P]` markers apply only to tasks touching disjoint files.
- No migration concern: T006 creates a first-time schema idempotently.
- Scope is bounded — no web UI, no automatic GPU provisioning, no LLM analysis, no observability stack.
- Data-safety-first ordering is respected: digest identity, atomic publication, and partial-file exclusion (T011/T013) precede any processing task.
- Secret handling is task-level rather than an afterthought (T010 bounded secret-scrubbed errors, T031 stderr-bounding tests, T034 secret-safe diagnostics).
- The MVP framing (Setup + Foundation + US1, then US2 with a fake worker) prioritizes user-critical behavior over polish.

## Evidence

Artifacts inspected (round 2):

- `specs/001-field-transcription-pipeline/tasks.md` (full re-read)
- Approved `spec.md` and `plan.md`, plus `data-model.md`, `research.md`, `quickstart.md`, `contracts/cli.md`, `contracts/transcript.schema.json`
- `.specify/memory/constitution.md`, `AGENTS.md`

Commands run:

- `python3 scripts/ai_flow.py claim` → `{"iteration": 2, "result": "claimed", "stage": "tasks"}`
- Round-1 repository checks retained: `cat .gitignore` (single entry `.ai-flow/` at the time of review) and `git status --short` (untracked `260811_0111.MP3`). T003 is the task that must fix this; the `.gitignore` file itself is unchanged as expected, since implementation has not started.

Not validated: no implementation exists, so no test or build command was applicable. Worker, GPU, and VPS environments were not inspected.

No specification, plan, task, implementation, or documentation file was modified. The task list is ready for implementation; the `Later` items are non-blocking follow-ups.
