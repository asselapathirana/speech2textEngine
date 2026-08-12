---
name: review-impl
description: Review implementation changes after Codex or Spec Kit has modified the project. Use when inspecting git status and diffs for bugs, unsafe migrations, broken references, permission mistakes, workflow regressions, weak tests, deployment risks, and scope creep.
---

# Review Implementation

Review the implementation only. Do not edit files, implement fixes, commit, push, migrate, delete files, or run destructive commands.

## Required Inspection

Run or inspect, when safe and available:

- `git status`
- The relevant Git diff against the repository's default branch or current baseline
- The project's smallest configured static or health check, only when available and safe
- Relevant focused tests only if safe, available, and not too slow

If a command is unsafe, unavailable, or too slow, do not run it. State what was skipped and why.

## Inputs to Inspect

Find the active feature folder in this order:

1. Read `.specify/feature.json` and use `feature_directory` if present.
2. If unavailable, inspect the current branch name and matching `specs/*` folder.
3. If still unclear, inspect the newest relevant `specs/*` folder and state the assumption.

Inspect:

- Active `spec.md`, `plan.md`, and `tasks.md`, if present
- `git status`
- Relevant Git diff against the repository's default branch or current baseline
- Relevant changed files from the diff
- Existing code context only as needed to confirm whether a finding is real

## Review Focus

Check for:

- Bugs, incomplete branches, edge-case failures, and inconsistent state handling.
- Broken imports, APIs, routes, resource references, configuration, or integration hooks.
- Unsafe, unnecessary, or under-explained migrations.
- Permission mistakes or missing enforcement at trust boundaries.
- Workflow regressions, invalid state transitions, or atomicity issues.
- Data validation, consistency, compatibility, and history/versioning errors.
- Security risks, including authorization bypass, unsafe inputs, and unintended data exposure.
- Missing, weak, misplaced, or non-deterministic tests.
- Deployment risks, missing settings, packaging issues, or environment assumptions.
- Scope creep beyond the active specification and project boundaries.
- User-critical regressions or missing primary paths.

## Output Format

Return a review report with these sections:

- `Critical`: Must fix before merge or demo because it can break correctness, security, data integrity, or deployment.
- `Important`: Should fix before merge because it is likely to cause bugs, regressions, or rework.
- `Later`: Can be deferred without blocking merge or demo.
- `Ignore`: Explicitly note concerns that were checked and are acceptable.

For each finding, include:

- File and line reference when available.
- The issue.
- Why it matters.
- A concise suggested fix direction, without editing code.

End with:

- Commands run and their result.
- Commands skipped and why.
- Whether the implementation appears ready for merge or not ready.
