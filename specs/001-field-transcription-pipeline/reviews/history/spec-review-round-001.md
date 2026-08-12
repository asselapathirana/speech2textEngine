# Spec Review

## Verdict

CHANGES_REQUIRED

## Critical

None.

## Important

1. **Upload completeness is never defined, so a partially transferred MP3 can be registered and processed.**
   - Artifact: `specs/001-field-transcription-pipeline/spec.md` — FR-002, FR-013, User Story 1 Acceptance Scenarios 2-3, Edge Cases ("An MP3 is incomplete...", "The network drops during laptop-to-VPS upload").
   - Issue: The spec requires a resumable upload into `incoming/` and separately requires job discovery/registration from that same area, but no requirement states how the controller distinguishes a still-in-flight or resumed partial transfer from a completed original. Verification that "the completed VPS file matches the source" (FR-002) is described as an owner-available capability, not as a precondition of registration.
   - Consequence: Discovery running during an upload can register a truncated file, produce a transcript that passes the non-empty/format checks of FR-011, and mark the job complete with silently missing audio; the alternative implementation (rejecting the partial as unreadable input) produces spurious failures for a transfer that would have succeeded. Both outcomes conflict with SC-002 and SC-003.
   - Correction: Add a functional requirement that a recording becomes eligible for job registration only after its transfer is established as complete (for example, staged transfer plus atomic move into `incoming/`, or size/digest agreement with the laptop source), and state the required behaviour when an incomplete transfer is observed.

2. **The lifecycle of `processed/` and `failed/` is unspecified and conflicts with the stated permanent location of the original.**
   - Artifact: `specs/001-field-transcription-pipeline/spec.md` — FR-004, FR-003, User Story 1 Acceptance Scenario 1, Data Integrity & Lifecycle Rules, Key Entities ("Recording ... permanent VPS location").
   - Issue: FR-004 mandates separate locations for processed recordings and failed-job material, but no requirement, scenario, or lifecycle rule states what is placed there, when, or by which stage. Acceptance Scenario 1.1 states the complete original is stored below `incoming/`, and the Recording entity records a single permanent VPS location, without saying whether that location changes on completion or failure.
   - Consequence: Implementations diverge on whether originals are relocated after processing. If they are, re-discovery and duplicate detection (FR-013, Acceptance Scenario 1.3) must recognise a recording that is no longer in `incoming/`, or a re-upload creates a second active job and a second transcript; if they are not, two required directories remain permanently unused and the requirement is untestable.
   - Correction: State explicitly whether the original stays in `incoming/` or is moved on completion/failure, what `failed/` holds, and how recording identity and duplicate detection remain valid across any relocation.

3. **The job-state model does not define claim recovery or a closed transition set, so its own acceptance criteria are not testable.**
   - Artifact: `specs/001-field-transcription-pipeline/spec.md` — FR-005, FR-006, User Story 3 Acceptance Scenario 3, Data Integrity & Lifecycle Rules ("at least pending, claimed/processing, complete, failed"), SC-004.
   - Issue: FR-006 requires claiming to prevent concurrent processing, and Acceptance Scenario 3.3 asserts that interrupted jobs "can be recovered or retried" after a controller restart, but no requirement defines when a job stranded in claimed/processing (killed controller, vanished worker) becomes retryable, or by what signal. The lifecycle rule fixes only a minimum state set with "at least", while SC-004 requires automated tests covering "every permitted job-state transition".
   - Consequence: A claimed job can remain permanently unprocessable while still blocking retry, which is the main failure mode of a disposable-worker design; and SC-004 cannot be evaluated because the permitted transition set is open-ended.
   - Correction: Enumerate the permitted states and transitions, and add a requirement describing how a stale claim is detected and returned to a retryable state (for example, claim ownership plus expiry, or an explicit owner-invoked reset).

## Later

1. FR-011 says "The system MUST copy results to the VPS" without naming the initiator, while the Credential and Data Safety section forbids giving the worker any credential that reaches back to the VPS. Reword FR-011 so the VPS-initiated pull is explicit and cannot be read as a worker push.
2. FR-012 preserves failed jobs for retry but sets no attempt ceiling or escalation, even though FR-005 records attempt count and GPU time is rented. Consider stating what happens after repeated failure of the same job.
3. FR-001 states MP3 "at 128 kbps" is accepted without saying whether other bitrates or WS-852 settings must be rejected. Clarify whether this is the expected input or an enforced constraint.
4. `idea.txt` specifies `/data/field-audio/...` and `/data/transcripts/`, while FR-003/FR-004 place everything below `/home/assela/field-transcriber/`. The spec Input records this as an owner instruction, so the spec is right; the divergence should be reconciled during planning so implementation does not silently follow `idea.txt` paths.
5. The collision rule and Edge Cases cover the same filename with different content, but not the same content arriving under a different filename. Worth stating whether that is a duplicate or a distinct recording.

## Ignore

- Retained technical prescriptions (large multilingual model, VAD, word timing, diarization, SSH transfer, JSON/Markdown/SRT outputs) are owner-supplied constraints per `AGENTS.md` and are appropriate to keep in the spec, as the checklist notes.
- Credential and data-safety rules are consistent with constitution principle IV; the worker is denied return credentials and images/repo must carry no field data (SC-005).
- Absence of a word-error-rate threshold and of formal throughput targets is deliberate and matches the project's pragmatic quality bar.
- Out-of-scope and Assumptions sections bound the feature clearly; LLM interpretation is correctly excluded while FR-016 preserves separation for later.
- Verification limited to presence, basic format, and non-empty content (rather than digest comparison of returned outputs) is acceptable at specification level.
- Single-recording, non-parallel processing and anonymous speaker labels are stated assumptions consistent with the user stories.
- Multi-language content within one recording is unaddressed, which is acceptable for a first version given FR-010 records detected language and confidence.

## Evidence

Artifacts inspected:

- `specs/001-field-transcription-pipeline/spec.md`
- `specs/001-field-transcription-pipeline/checklists/requirements.md`
- `.specify/feature.json` (confirmed active feature directory)
- `.specify/memory/constitution.md`
- `idea.txt`, `AGENTS.md`, `CODEX_HANDOFF.md` (project scope and terminology only)

Commands run:

- `python3 scripts/ai_flow.py claim` → `{"iteration": 1, "result": "claimed", "stage": "spec"}`
- `cat .ai-flow/flow.json`, `find specs -type f`, `ls -R docs`

No specification, plan, task, implementation, or documentation file was modified. No build or test commands were applicable at this stage.
