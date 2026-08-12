---
name: review-spec
description: Review the current Spec Kit specification before planning. Use when checking spec.md for scope clarity, testability, contradictions, acceptance criteria, project boundaries, data ownership, and workflow assumptions before running the Spec Kit planning stage.
---

# Review Spec

Review the active Spec Kit specification only. Do not edit files, implement changes, create tasks, or propose new features except to identify accidental scope creep that should be removed, deferred, or clarified.

## Inputs to Inspect

Find the active feature folder in this order:

1. Read `.specify/feature.json` and use `feature_directory` if present.
2. If unavailable, inspect the current branch name and matching `specs/*` folder.
3. If still unclear, inspect the newest relevant `specs/*/spec.md` and state the assumption.

Inspect:

- Active `spec.md`
- `checklists/requirements.md`, if present
- Related project context only as needed to verify app bounds and terminology

## Review Focus

Check for:

- Clear feature scope and explicit non-goals.
- Testable, unambiguous functional requirements.
- Contradictions between user stories, requirements, assumptions, and success criteria.
- Missing acceptance criteria for primary workflows and important edge cases.
- Overpromising beyond the stated project scope or user needs.
- Client-facing ambiguity in wording, workflow outcomes, or validation behavior.
- Unclear user roles, data ownership, or permissions.
- Unclear data lifecycle, lineage, retention, or workflow assumptions.
- Technology, migration, compatibility, security, test, and operational risks, stated at specification level only.

## Output Format

Return a review report with these sections:

- `Critical`: Must fix before planning because the spec is unsafe, contradictory, or materially incomplete.
- `Important`: Should fix before planning because it may cause wrong implementation or rework.
- `Later`: Can be deferred without blocking planning.
- `Ignore`: Explicitly note concerns that were checked and are acceptable.

For each finding, include:

- Artifact and section or line reference when available.
- The issue.
- Why it matters.
- A concise suggested correction or clarification.

If there are no blocking issues, say the spec is ready for planning and list any minor follow-ups separately.
