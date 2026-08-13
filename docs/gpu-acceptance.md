# GPU Acceptance Record

## Status

**DEFERRED, NOT PASSED**

On 2026-08-12, the owner directed closure of feature
`001-field-transcription-pipeline` without renting a manually managed GPU worker.
The acceptance run is deferred to feature `002-runpod-serverless`, which will add
on-demand disposable GPU execution and automatic scale-down.

## Evidence Available

- 32 dependency-free controller and worker-normalization tests passed.
- Shell syntax checks passed for upload, worker entrypoint, local/worker checks,
  and deployment scripts.
- Python byte-compilation passed with bytecode redirected to temporary storage.
- `git diff --check` passed.
- The representative MP3 remains ignored by Git.

## Evidence Not Yet Available

- Worker image identifier and image credential/data inspection result.
- Real GPU model loading and CUDA execution.
- End-to-end wall time and peak GPU memory.
- Remote cleanup outcome.
- Outdoor-audio transcript observations for wind, walking, distant speakers,
  speaker changes, and overlapping speech.

## Release Boundary

Feature `001` may be reviewed as a locally validated implementation, but the
pipeline must not be treated as field-ready until the deferred checks above are
completed and recorded through feature `002`.
# Feature 002 Runpod acceptance

## Status

**PASSED on 2026-08-13 for the representative acceptance recording.** The owner
authorized one charged Runpod run and external transfer of the selected recording.

## Configuration and evidence

- Image: `assela/field-transcriber-worker:2026-08-13`, registry digest
  `sha256:d5b26f35d8a5151a150c9a6bd4d6505173690ab2601ab55ded226a1b5a5c6b85`.
- Endpoint: `dg4h1h8d0xymig`; minimum workers `0`, maximum workers `1`, idle
  timeout `5` seconds, execution timeout `7,200,000` ms, and 24 GB GPU priority
  (RTX 4090, RTX A5000, RTX 3090).
- R2 transport: private EU-jurisdiction bucket; authenticated PUT, HEAD, GET,
  digest comparison, and DELETE passed before the recording run.
- Recording SHA-256:
  `6eaf895ce5ac50d32d3eecfce5ca0ab8883e5d36b4ad45402aaf4e1ca2feadca`.
- Successful remote execution: queue delay `1.206` seconds, execution duration
  `10.465` seconds, Whisper `large-v3`, float16, peak GPU memory `2,363` MB.
- Outputs: authoritative JSON plus non-empty Markdown and SRT derivatives were
  validated and published; the unchanged input moved to `processed/`.
- Cleanup: both temporary transfer objects were deleted and the Runpod worker
  returned to `EXITED` with zero minimum workers.

The first intended attempt failed because Hugging Face gated-model access had not
yet been granted. After access was granted, a retry completed. The live run also
exposed an object-visibility race and stale-attempt reconciliation defect. Both
received regression coverage and controller fixes before acceptance closure.

## Boundary

This validates one representative short recording and the restartable serverless
transport path. It does not establish transcription quality for every outdoor
condition, language, overlap pattern, or recording length. Runpod did not echo an
explicit datacenter restriction in the created endpoint response, so EU storage
residency is verified for R2, but GPU processing location is not asserted as EU-only.
