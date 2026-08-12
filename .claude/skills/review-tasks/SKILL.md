---
name: review-tasks
description: Review the current Spec Kit tasks.md before implementation. Use when checking that tasks are small, testable, safely ordered, scope-bound, migration-conscious, test-covered, cleanup-separated, and prioritized for user-critical work.
---

# Review Tasks

Review the active Spec Kit task list only. Do not edit files, implement changes, reorder tasks yourself, or propose new features except to identify accidental scope creep that should be removed, deferred, or clarified.

## Inputs to Inspect

Find the active feature folder in this order:

1. Read `.specify/feature.json` and use `feature_directory` if present.
2. If unavailable, inspect the current branch name and matching `specs/*` folder.
3. If still unclear, inspect the newest relevant `specs/*` folder and state the assumption.

Inspect:

- Active `spec.md`
- Active `plan.md`
- Active `tasks.md`
- Supporting artifacts such as `data-model.md`, `contracts/`, and `quickstart.md`, if present
- Existing code context only as needed to validate task ordering and risk

## Review Focus

Check whether tasks:

- Are small enough to implement and review independently.
- Are testable, with clear expected outcomes.
- Follow a safe order: tests before behavior, data safety before UI, permissions before exposure, validation before approval.
- Separate cleanup/refactor work from feature delivery.
- Avoid migrations unless explicitly required and justified by the plan.
- Include tests where needed for permissions, workflow, validation, data lifecycle, history, and user flows.
- Do not silently expand scope beyond the specification or project boundaries.
- Prioritize user-critical behavior over polish.
- Avoid broad or destructive operations.
- Keep architecture, data integrity, permissions, workflow, deployment, compatibility, and test risks visible.

## Output Format

Return a review report with these sections:

- `Critical`: Must fix before implementation because task execution is unsafe, unordered, or materially incomplete.
- `Important`: Should fix before implementation because it may cause rework, weak tests, or demo risk.
- `Later`: Can be deferred without blocking implementation.
- `Ignore`: Explicitly note concerns that were checked and are acceptable.

For each finding, include:

- Artifact and task reference when available.
- The issue.
- Why it matters.
- A concise suggested correction, split, removal, or reorder.

If there are no blocking issues, say the tasks are ready for implementation and list any minor follow-ups separately.
