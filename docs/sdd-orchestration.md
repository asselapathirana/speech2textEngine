# Cross-CLI SDD Orchestration

The cross-CLI workflow coordinates Codex artifact creation with independent Claude
Code review. It reuses the existing Spec Kit and `review-*` skills rather than
replacing their instructions.

## Starting a Flow

Open Codex and Claude Code in the same repository worktree. The commands may be
started in either order because each side waits for the other.

In Codex:

```text
$start-sdd <feature description>
```

In Claude Code:

```text
/review-sdd
```

Only these two initial commands are normally required. Codex progresses through
specification, plan, tasks, and implementation. Claude reviews each published
stage and then waits for the next one.

```text
Codex                         Shared state                    Claude
  | create/revise artifact        |                              |
  | publish stage --------------> | *.ready                     |
  |                               | <-------------- claim stage |
  | wait for verdict              | *.reviewing                  |
  |                               | <------- report + status     |
  | read verdict <--------------- |                              |
  | continue or revise            |                              |
```

## Verdicts

Claude publishes one exact machine-readable status:

- `APPROVED`: Codex continues to the next stage.
- `CHANGES_REQUIRED`: Codex addresses `Critical` and `Important` findings, then
  republishes the same stage.
- `HUMAN_REVIEW`: both automated loops stop for an owner decision.

The default maximum is four review rounds per stage. A further blocking verdict is
escalated to `HUMAN_REVIEW` rather than creating an unbounded revision loop.

## Runtime State

`scripts/ai_flow.py` owns all state transitions and atomic marker changes under
`.ai-flow/`. The directory is local runtime state and is ignored by Git.

Useful inspection commands:

```bash
python3 scripts/ai_flow.py status
python3 scripts/ai_flow.py --help
```

The latest review is available at `.ai-flow/<stage>-review.md`. Earlier review
rounds are archived under `.ai-flow/history/` for the duration of the flow.

## Recovery

Both skills resume persisted state after an interrupted CLI session. Run the same
skill again; do not delete or edit marker files manually.

If Claude fails after claiming a stage but before publishing its report, return the
claim and restart `/review-sdd`:

```bash
python3 scripts/ai_flow.py release <stage>
```

After a `HUMAN_REVIEW` decision, Codex records the owner's `APPROVED` or
`CHANGES_REQUIRED` choice through `resolve-human` and resumes the flow.

Start a separate flow only after preserving any review evidence that is needed:

```bash
python3 scripts/ai_flow.py reset --confirm
```

The orchestration does not commit, push, create or merge pull requests, or deploy.
Those actions remain explicit owner decisions.
