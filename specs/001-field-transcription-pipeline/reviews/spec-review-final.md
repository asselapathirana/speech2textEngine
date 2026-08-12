# Spec Review

## Verdict

APPROVED

## Critical

None.

## Important

None. All three round-1 findings are resolved:

1. Upload completeness — FR-017 introduces a `uploading/` staging area, digest-and-size agreement with the laptop source, and atomic publication into `incoming/`; User Story 1 Acceptance Scenarios 1-2, the Input/Output boundaries, and a new edge case ("Discovery runs while a resumable upload is still in progress") now agree that discovery ignores partial files.
2. `processed/` and `failed/` lifecycle — the Data Integrity rules now state that a verified recording starts in `incoming/`, moves to `processed/` on completion, stays in `incoming/` on a retryable failure, and moves to `failed/` only when the owner declares the input non-retryable; recording identity is retained across relocation and duplicate detection searches all lifecycle locations by content digest.
3. Job-state model — the state set is now closed (`pending`, `processing`, `failed`, `complete`) with an enumerated transition list, and FR-018 defines claim ownership tokens, renewal, expiry detection on startup, and transition of expired claims to the retryable `failed` state. SC-004 is now evaluable against a finite transition set.

Re-checked for contradictions introduced by the revision: the new transition set is consistent with User Story 2 Acceptance Scenario 3 and User Story 3 Acceptance Scenarios 2-3; digest-based duplicate detection also resolves the round-1 `Later` item about identical content arriving under a different filename.

## Later

1. FR-011 still says "The system MUST copy results to the VPS" without naming the initiator, while the Credential and Data Safety section forbids giving the worker credentials that reach back to the VPS. Reword so the VPS-initiated pull is explicit.
2. FR-012 sets no attempt ceiling or escalation for a job that fails repeatedly, even though FR-005 records attempt count and GPU time is rented.
3. FR-001 states MP3 "at 128 kbps" without saying whether other bitrates must be rejected.
4. FR-004 enumerates the required field-data locations but omits the `uploading/` staging area that FR-017 now mandates; the Assumptions list does include it. Worth aligning FR-004 for consistency.
5. Input rejected as unsupported or unreadable lands in `failed`, which the transition set allows to return to `pending`. There is no terminal "will not process" state; the owner-declared non-retryable path is described only as a file relocation. Acceptable for a single-operator tool, but planning should decide how such a job is prevented from being retried indefinitely.
6. `idea.txt` still specifies `/data/field-audio/...` and `/data/transcripts/`, while FR-003/FR-004 place everything below `/home/assela/field-transcriber/`. The spec Input records this as an owner instruction; the divergence should be reconciled during planning so implementation does not silently follow `idea.txt` paths.

## Ignore

- Retained technical prescriptions (large multilingual model, VAD, word timing, diarization, SSH transfer, JSON/Markdown/SRT outputs) are owner-supplied constraints per `AGENTS.md` and appropriately kept in the spec.
- Credential and data-safety rules remain consistent with constitution principle IV.
- Absence of a word-error-rate threshold and of formal throughput targets is deliberate and matches the project's pragmatic quality bar.
- Out-of-scope and Assumptions sections bound the feature clearly; FR-016 preserves separation for later LLM analysis without pulling it into scope.
- Result verification limited to presence, basic format, and non-empty content is acceptable at specification level.
- Single-recording, non-parallel processing and anonymous speaker labels are stated assumptions consistent with the user stories.
- Multi-language content within one recording is unaddressed, which is acceptable given FR-010 records detected language and confidence.
- A completed recording re-uploaded later would exist in both `incoming/` and `processed/`; duplicate detection still prevents a second active job, so this is cosmetic.

## Evidence

Artifacts inspected (round 2):

- `specs/001-field-transcription-pipeline/spec.md` (full re-read after revision)
- `specs/001-field-transcription-pipeline/checklists/requirements.md`
- `.specify/feature.json`, `.specify/memory/constitution.md`
- `idea.txt`, `AGENTS.md` (scope and terminology only)

Commands run:

- `python3 scripts/ai_flow.py claim` → `{"iteration": 2, "result": "claimed", "stage": "spec"}`
- `git diff --stat` (no tracked-file changes; the feature is untracked)

No specification, plan, task, implementation, or documentation file was modified. The spec is ready for planning; the `Later` items above are non-blocking follow-ups.
