---
name: review-plan
description: Review the current Spec Kit implementation plan before tasks are generated. Use when checking plan.md for fit with the existing codebase, project scope, data and permission assumptions, migrations, deployment, and operational readiness.
---

# Review Plan

Review the active Spec Kit implementation plan only. Do not edit files, implement changes, generate tasks, or propose new features except to identify accidental scope creep that should be removed, deferred, or clarified.

## Inputs to Inspect

Find the active feature folder in this order:

1. Read `.specify/feature.json` and use `feature_directory` if present.
2. If unavailable, inspect the current branch name and matching `specs/*` folder.
3. If still unclear, inspect the newest relevant `specs/*` folder and state the assumption.

Inspect:

- Active `spec.md`
- Active `plan.md`
- `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`, if present
- Existing architecture, data, permission, migration, deployment, and test context only as needed

## Review Focus

Check whether the plan:

- Fits the existing codebase and established module boundaries.
- Avoids unnecessary new features, abstractions, dependencies, or UI scope.
- Keeps migrations minimal and justified, with clear data-safety reasoning.
- Uses roles and permissions correctly where applicable.
- Respects existing workflow assumptions and state transitions.
- Handles data lifecycle, history, migration, and retirement coherently.
- Identifies data integrity and validation boundaries.
- Avoids duplicating established domain logic without justification.
- Notes deployment, environment, compatibility, and rollback risks where relevant.
- Preserves project scope and operational readiness.
- Includes a credible testing strategy before implementation.

## Output Format

Return a review report with these sections:

- `Critical`: Must fix before task generation because the plan is unsafe, inconsistent with the spec, or likely to break the app.
- `Important`: Should fix before task generation because it may cause rework or weak implementation.
- `Later`: Can be deferred without blocking task generation.
- `Ignore`: Explicitly note concerns that were checked and are acceptable.

For each finding, include:

- Artifact and section or line reference when available.
- The issue.
- Why it matters.
- A concise suggested correction or clarification.

If there are no blocking issues, say the plan is ready for task generation and list any minor follow-ups separately.
