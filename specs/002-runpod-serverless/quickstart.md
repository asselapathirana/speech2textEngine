# Quickstart Validation: Runpod Serverless

## Implementation evidence

- Runpod worker SDK dependency: owner approved on 2026-08-12; requirement may be
  added, but the implementation workflow must not install it.
- Automated checks: 71 tests passed on 2026-08-12 after implementation review fixes. Shell syntax checks, Python
  compilation with external bytecode cache, and `git diff --check` also passed.
- Credential and data inspection: configuration contains only secret variable
  names; test JSON excludes credentials and signed URLs. Final tracked-file scan
  found no persisted runtime secret or signed URL. The example file contains only
  secret environment-variable names.
- Owner-run Runpod/GPU acceptance: deferred, not passed.

## 1. Local deterministic checks

Run the complete standard-library suite:

```bash
/home/assela/python/.venv/bin/python -B -m unittest discover -s tests -v
```

Expected: fake-provider, object signing, state mapping, restart reconciliation,
cancellation, indeterminate resolution, cleanup, existing SSH behavior, transcript
validation, and rendering tests pass without network or GPU access.

## 2. Configure without committing secrets

Create an untracked `config.env` selecting `runpod` mode and naming environment
variables that hold the Runpod API key, S3-compatible access key and secret, and
Hugging Face token. Configure endpoint ID, object-store endpoint/bucket/region,
`7200000` ms execution timeout, `10800000` ms TTL, and one-worker concurrency.

Expected: configuration validation rejects embedded secrets, non-positive or
provider-invalid limits, non-HTTPS endpoints outside explicit local tests, and a
TTL not greater than the execution timeout. Two and three hours are initial
defaults, not permanent lower bounds after measured owner adjustment.

## 3. Validate endpoint settings

Before uploading field audio, inspect the selected endpoint in the Runpod console
or API and record evidence that:

- active workers is `0`;
- maximum workers is `1`;
- idle timeout is short (target `5` seconds);
- requested execution timeout supports at least two hours;
- job TTL supports at least three hours;
- selected GPU priority includes a compatible 24 GB class.

## 4. Validate transient object transport

Using a non-sensitive fixture, exercise upload, presigned GET, presigned PUT,
download, digest verification, and deletion. Confirm URLs address only their one
object and expire after the configured window.

Expected: no object remains after success. In a simulated failed attempt, the
object remains only until the configured diagnostic retention expires, after which
`cleanup-transfers` deletes it.

## 5. Run the representative recording

With explicit owner authorization for provider charges and external field-audio
transfer:

```bash
python3 -m field_transcriber --config config.env run-next --json
```

Expected:

1. One local attempt and one remote execution are persisted.
2. No worker was active before submission; one compatible worker starts on demand.
3. The worker verifies the MP3 digest, transcribes, and uploads canonical JSON.
4. The VPS retrieves and validates JSON, generates Markdown/SRT, completes the
   local job, and deletes both transfer objects.
5. Runpod returns to zero active workers after the idle interval.

Record endpoint/configuration evidence, GPU class, queue time, startup time,
processing time, transfer time, total wall time, peak GPU memory, cleanup result,
scale-down delay, and transcript limitations in `docs/gpu-acceptance.md`.

## 6. Recovery checks

- Stop the controller after submission, restart it, and verify it reconciles the
  same external ID without another `/run` call. Drive this through
  `field_transcriber.cli.main`, not only the lower-level orchestrator.
- Repeat recovery after provider status retention expires while a valid result
  object remains; verify result-first reconciliation completes without another GPU
  submission.
- Restart while status is queued/running and verify the same attempt receives a
  renewed local claim before expired-claim recovery.
- Force an uncertain submission and verify no automatic retry occurs. After the
  deadline, test both `resolve-remote` decisions.
- Race `cancel` with a completed fake result and verify valid success wins.
- Force result expiry and verify an actionable retryable failure.

## 7. Credential and data inspection

Inspect tracked files, image history, logs, SQLite rows, provider results, and the
temporary bucket. Expected: no API keys, bucket credentials, signed URLs, VPS
credentials, residual field audio, or residual transcript objects remain where
prohibited.
