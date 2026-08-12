# Speech2Text Project Constitution

## Core Principles

### I. Clear Scope and a Working End-to-End Path

Each feature MUST state the workflow it enables, what constitutes a useful working
result, important failure behaviour, and relevant non-goals. Planning SHOULD be
proportionate to the small, owner-operated nature of the project. Unknown decisions
that materially affect scope, data safety, credentials, or cost MUST be clarified;
minor implementation details may be resolved pragmatically and documented.

### II. Minimal and Reusable Design

Changes MUST be focused, avoid duplicated logic, and reuse existing modules before
introducing new abstractions. New dependencies MUST have a documented need and
owner approval. Environment-specific values and secrets MUST remain configurable.

### III. Risk-Based Testing

TDD is recommended for job-state transitions, retry/idempotency behavior, output
generation, and other logic where regression is likely. A failing test first is
preferred when practical, but is not a universal gate. Small scripts, configuration,
and external GPU integrations MAY use tests added alongside implementation or a
documented manual check. Each feature MUST receive the smallest meaningful
validation, and skipped checks MUST be reported.

### IV. Audio, Transcript, and Credential Safety

Original recordings MUST remain unchanged, and generated analysis MUST not overwrite
the authoritative transcript. Secrets and field data MUST not be committed or baked
into the worker image. The VPS MUST control the disposable GPU worker without giving
that worker credentials that grant access back to the VPS. Other security controls
SHOULD be added where the actual threat or deployment context justifies them.

### V. Restartable, Understandable Operation

The processing workflow MUST be restartable, preserve failed jobs for diagnosis or
retry, and verify result transfer before marking work complete. Errors SHOULD be
clear enough for the owner to act on them. Lightweight logs and SQLite state are
preferred over production monitoring infrastructure. Formal performance testing,
rollback plans, and operational hardening are required only when a feature's risk
or cost warrants them.

## Development Workflow

- Specifications, plans, and tasks MUST remain consistent with one another.
- Tasks SHOULD include focused automated tests for important pure logic and state
  transitions. Test-first ordering is preferred, not mandatory.
- Relevant checks MUST run before handoff; skipped checks and reasons MUST be recorded.
- A representative local or mocked integration check is normally sufficient during
  development. Real rented-GPU and challenging outdoor-audio validation may remain
  an explicit owner-run acceptance step.
- Destructive operations, dependency installation, commits, pushes, and deployments require explicit owner authorization.

## Governance

This constitution governs Spec Kit artifacts and feature review. Amendments require
an explicit rationale and corresponding updates to affected templates or guidance.

**Version**: 1.1.0 | **Ratified**: 2026-08-11 | **Last Amended**: 2026-08-11
