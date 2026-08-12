# Data Model: Field Audio Transcription Pipeline

## Recording

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | Primary key |
| `sha256` | text | 64 lowercase hex characters; unique stable identity |
| `original_name` | text | Non-empty basename, no directory components |
| `size_bytes` | integer | Greater than zero |
| `status` | text | `incoming`, `processed`, or `quarantined` |
| `current_path` | text | Unique path below the configured files root |
| `ingested_at` | timestamp | UTC ISO-8601 |
| `updated_at` | timestamp | UTC ISO-8601 |

A recording has exactly one job. A digest already known under any name or lifecycle
location resolves to the existing recording. A target filename occupied by a
different digest is a collision and cannot be published automatically.

## Job

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | Primary key |
| `recording_id` | integer | Unique foreign key to Recording |
| `status` | text | `pending`, `processing`, `failed`, or `complete` |
| `attempt_count` | integer | Starts at zero; increments on claim |
| `claim_token` | text/null | Required only while processing; unpredictable |
| `claim_expires_at` | timestamp/null | Required only while processing; renewed every heartbeat interval |
| `latest_error_step` | text/null | Bounded step identifier |
| `latest_error` | text/null | Bounded actionable detail without secrets |
| `created_at` | timestamp | UTC ISO-8601 |
| `updated_at` | timestamp | UTC ISO-8601 |
| `completed_at` | timestamp/null | Set only for complete jobs |

### State transitions

```text
pending ──claim──> processing ──verified completion──> complete
                         │
                         ├──step failure─────────────> failed
                         └──claim expiry─────────────> failed

failed ──explicit retry──> pending
```

No other transitions are valid. Claim, renewal, failure, retry, and completion
each run in a single SQLite transaction with an expected-current-state predicate.
Renewal updates the expiry only when both `status = processing` and `claim_token`
match. Default lease duration is five minutes and default renewal interval is 60
seconds; both are configuration values and the interval must remain below the lease.

## Attempt

| Field | Type | Rules |
| --- | --- | --- |
| `id` | integer | Primary key |
| `job_id` | integer | Foreign key to Job |
| `number` | integer | Unique with job; equals incremented attempt count |
| `claim_token` | text | Identifies the controller claim |
| `worker_host` | text | Non-secret configured host label |
| `started_at` | timestamp | UTC ISO-8601 |
| `finished_at` | timestamp/null | Set on failure or completion |
| `outcome` | text/null | `failed` or `complete` when finished |
| `error_step` | text/null | Failed orchestration step |
| `error_detail` | text/null | Bounded stderr/message, scrubbed of secrets |
| `cleanup_status` | text/null | `complete`, `failed`, or `not_attempted` |
| `duration_seconds` | real/null | Worker-reported or controller wall time |
| `peak_gpu_memory_mb` | integer/null | Worker-reported when available |

## Transcript document

The canonical JSON is stored as a file and validated against
`contracts/transcript.schema.json`; it is not duplicated into SQLite.

- One transcript belongs to one recording digest and one successful attempt.
- It contains detected language, available language confidence, model/run metadata,
  ordered segments, and ordered words.
- Each segment has start/end seconds, speaker label, text, and words.
- Words may have unavailable timing or confidence represented explicitly as null;
  the renderer must not invent values.
- Completion requires at least one segment whose trimmed text is non-empty. A
  document without such a segment is retained as attempt diagnostics and produces
  the retryable error `no_speech_detected`, not a Transcript entity.
- Markdown and SRT are derived deterministically from this document.

## Filesystem lifecycle

```text
uploading/<name>.partial  --verify + atomic publish--> incoming/<name>
incoming/<name>          --verified job completion--> processed/<name>
incoming/<name>          --owner quarantine--------> failed/<name>
result staging           --schema/render checks----> transcripts/<digest>/
```

The database path update and job completion occur only after transcript publication
is ready. Recovery checks reconcile a safely moved source or published transcript
after an interruption before repeating work.
