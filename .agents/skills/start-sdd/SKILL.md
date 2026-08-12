---
name: start-sdd
description: Run the full Spec Kit SDD workflow with Claude Code as a file-coordinated reviewer. Use when the user invokes $start-sdd with a feature description and wants specify, plan, tasks, and implementation to alternate automatically with /review-sdd.
---

# Start SDD

Coordinate the existing Spec Kit skills with Claude Code. This skill owns artifact
creation and revision. Claude's `/review-sdd` owns independent review. Do not
replace, summarize, or weaken either side's underlying skill instructions.

## Inputs

Treat `$ARGUMENTS` as the feature description.

- A new flow requires a non-empty feature description.
- A resumed flow may omit it because the active feature and artifacts already
  exist.
- Work from the repository root and use `python3`.

## Authoritative Stage Skills

For each stage, read and follow the named skill in full:

| Stage | Skill |
| --- | --- |
| `spec` | `.agents/skills/speckit-specify/SKILL.md` |
| `plan` | `.agents/skills/speckit-plan/SKILL.md` |
| `tasks` | `.agents/skills/speckit-tasks/SKILL.md` |
| `implementation` | `.agents/skills/speckit-implement/SKILL.md` |

Pass the original feature description to the specification workflow. Later stages
must use the active feature selected by `.specify/feature.json`.

## Start or Resume

1. Run:

   ```bash
   python3 scripts/ai_flow.py init
   ```

2. Inspect the returned state.
3. If it was newly initialized and `$ARGUMENTS` is empty, stop with a clear error.
4. If the flow is `complete`, do not erase it automatically. Tell the owner that a
   new run requires:

   ```bash
   python3 scripts/ai_flow.py reset --confirm
   ```

5. If the flow is `human_review`, read the current review report and ask the owner
   for one of two explicit decisions: `APPROVED` or `CHANGES_REQUIRED`. After the
   decision, run:

   ```bash
   python3 scripts/ai_flow.py resolve-human <stage> <decision>
   ```

   For `CHANGES_REQUIRED`, apply both the report and the owner's direction before
   republishing. If the owner does not make either decision, leave the flow
   unchanged.

6. Resume from the persisted stage status. Never repeat a stage whose artifacts
   are already waiting for review or under review.

## Stage Loop

Process `spec`, `plan`, `tasks`, then `implementation`.

For a pending stage:

1. Read its authoritative skill.
2. Execute that skill completely, including its checks and any required user
   clarification.
3. Publish the completed artifacts:

   ```bash
   python3 scripts/ai_flow.py publish <stage>
   ```

For a stage already marked `waiting_review` or `reviewing`, do not alter its
artifacts. Continue directly to the wait.

Wait for Claude:

```bash
python3 scripts/ai_flow.py wait-review <stage> --value-only
```

Keep the command alive and poll its shell session when necessary. Do not substitute
a fixed sleep or ask the owner to relay Claude's verdict.

Handle the exact returned value:

- `APPROVED`: continue to the next stage.
- `CHANGES_REQUIRED`: read `.ai-flow/<stage>-review.md`, address every `Critical`
  and `Important` finding, rerun the checks required by that stage, publish the
  same stage again, and wait again. Do not implement `Later` findings.
- `HUMAN_REVIEW`: stop automation, show the report path and a concise explanation,
  then ask the owner for an explicit decision as described above.

## Revision Boundaries

Keep revisions confined to the artifact under review:

- `spec`: update the specification and its quality checklist.
- `plan`: update `plan.md` and only the associated design artifacts implicated by
  a blocking finding.
- `tasks`: update `tasks.md`.
- `implementation`: update implementation, tests, and directly affected
  documentation; run the smallest relevant validation required by the project.

If a finding conflicts with the user's requirements, constitution, or repository
instructions, treat it as `HUMAN_REVIEW` rather than silently choosing a side.

## Completion and Stops

After `implementation` is approved, run:

```bash
python3 scripts/ai_flow.py finish
```

Then report the completed stages and validation evidence.

Stop and involve the owner only for:

- clarification required by an authoritative stage skill;
- `HUMAN_REVIEW`;
- a fatal command, environment, or repository-state failure.

Do not start Claude Code, commit, push, open or merge a pull request, deploy, or
reset orchestration state unless the owner explicitly requests it.
