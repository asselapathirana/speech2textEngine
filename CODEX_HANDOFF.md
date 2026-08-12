# Codex Handoff

## Current State

The project-neutral Codex/Claude Spec Kit SDD workflow was copied into this
folder on 2026-08-11.

Installed components:

- `.agents/skills/`: Codex Spec Kit skills and `$start-sdd`
- `.claude/skills/`: independent Claude review skills and `/review-sdd`
- `.specify/`: Spec Kit scripts, templates, integration metadata, and a starter constitution
- `scripts/ai_flow.py`: dependency-free shared review state machine
- `docs/sdd-orchestration.md`: operating instructions
- `AGENTS.md` and `CLAUDE.md`: project-neutral working agreements
- `.gitignore`: ignores local `.ai-flow/` runtime state

The existing `260811_0111.MP3` and `idea.txt` files were preserved.

## Adaptations Already Made

- Removed LMS, Django, GeoDjango, PostGIS, parcel, CRS, and Dokku assumptions.
- Replaced project-specific review criteria with generic architecture, data,
  compatibility, security, testing, and operational criteria.
- Changed orchestration commands from `./.venv/bin/python` to `python3`.
- Did not copy `.specify/feature.json` or `.ai-flow/`, so no old feature or review
  state carries into this project.
- Validated `scripts/ai_flow.py` initialization/status behavior in a temporary
  directory and ran `bash -n` successfully on all `.specify` shell scripts.

## Required Before First Feature

This folder was not a Git repository at handoff time. Spec Kit uses Git branches,
so initialize the repository first:

```bash
cd /mnt/e/learn/speech2text
git init
```

The project-specific section of `AGENTS.md` and the constitution have now been
updated from `idea.txt`. Refine exact dependency versions and test commands once
the first implementation feature selects them.

## Project Customization (2026-08-11)

The working agreements, constitution, and Spec Kit templates have been tailored to
the field-audio transcription pipeline. The quality bar is deliberately pragmatic:
the end-to-end workflow should work reliably, and TDD is recommended for risky
logic and state transitions, but production-grade hardening, exhaustive coverage,
formal performance evidence, and heavyweight operational controls are not default
requirements. Audio preservation, transcript authority, restartability, verified
transfers, and the VPS/GPU credential boundary remain non-negotiable.

## Resume the Workflow

Open Codex and Claude Code in this same folder/worktree.

In Codex:

```text
$start-sdd <feature description>
```

In Claude Code:

```text
/review-sdd
```

Both commands may be started in either order. They coordinate through `.ai-flow/`.
Do not edit `.ai-flow` marker files manually.

Useful status command:

```bash
python3 scripts/ai_flow.py status
```

No dependencies were installed, no Git repository was initialized, and no feature
implementation was started during the transplant.
