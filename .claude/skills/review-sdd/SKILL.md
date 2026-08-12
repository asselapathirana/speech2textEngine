---
name: review-sdd
description: Continuously review Codex-produced Spec Kit artifacts through specification, plan, tasks, and implementation stages using the existing review rubrics and machine-readable shared statuses.
---

# Review SDD

Act as the independent reviewer in the shared SDD workflow. One `/review-sdd`
invocation remains active, alternately waiting for Codex and reviewing each
published stage. Do not create or revise the feature artifacts.

## Authoritative Review Skills

For each claimed stage, read and apply the named review skill in full:

| Stage | Review skill |
| --- | --- |
| `spec` | `.claude/skills/review-spec/SKILL.md` |
| `plan` | `.claude/skills/review-plan/SKILL.md` |
| `tasks` | `.claude/skills/review-tasks/SKILL.md` |
| `implementation` | `.claude/skills/review-impl/SKILL.md` |

These rubrics remain authoritative. This skill adds waiting, status selection, and
machine-readable handoff only.

## Wait and Claim

Work from the same repository root and worktree as Codex. Use Python 3:

```bash
python3 scripts/ai_flow.py claim
```

The command intentionally waits when Codex has not initialized or published a
stage. Keep it alive and poll its shell session when necessary.

The JSON result is one of:

- `claimed` or `resumed`, with a `stage` and `iteration`: perform that review.
- `terminal` with `human_review`: report that owner input is required and stop.
- `terminal` with `complete`: report completion and stop.

A `resumed` claim means this reviewer already owns an interrupted review. Reinspect
the current artifacts before completing it.

## Review and Verdict

Review only the claimed stage. Do not edit specifications, plans, tasks,
implementation, tests, or application documentation. Writing the orchestration
review report is the sole file-edit exception.

Select exactly one verdict:

- `CHANGES_REQUIRED` when at least one `Critical` or `Important` finding exists.
- `APPROVED` when only `Later` or `Ignore` notes exist, or no findings exist.
- `HUMAN_REVIEW` when a safe verdict requires an owner decision, requirements
  conflict, or essential evidence cannot be obtained without unsafe action.

Write the complete report to a temporary file, then atomically rename it to:

```text
.ai-flow/<stage>-review.md
```

Use this structure:

```markdown
# <Stage> Review

## Verdict

<APPROVED | CHANGES_REQUIRED | HUMAN_REVIEW>

## Critical

<findings or "None.">

## Important

<findings or "None.">

## Later

<findings or "None.">

## Ignore

<checks that were acceptable or "None.">

## Evidence

<artifacts inspected and commands run>
```

Each finding must include the artifact reference, issue, consequence, and concise
correction required by the underlying review skill. Do not promote optional
improvements into blocking findings.

## Publish and Continue

After the report is fully written, publish the verdict only through:

```bash
python3 scripts/ai_flow.py complete <stage> <verdict>
```

Never write `*.status`, `*.ready`, `*.reviewing`, `*.iteration`, or `flow.json`
directly. Use the final `status` returned by the helper because the iteration guard
may escalate `CHANGES_REQUIRED` to `HUMAN_REVIEW`.

- If the final status is `HUMAN_REVIEW`, report the reason and stop.
- If `implementation` is `APPROVED`, report that the final review is published and
  stop. Codex will mark the flow complete.
- Otherwise, return immediately to `claim` and wait for Codex's next publication.

If a fatal failure occurs before `complete`, return the claim with:

```bash
python3 scripts/ai_flow.py release <stage>
```

Then report the failure. Do not release a claim merely because the shell command
yielded or the review takes multiple tool calls.
