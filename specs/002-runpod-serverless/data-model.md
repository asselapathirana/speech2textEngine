# Data Model: Disposable Serverless GPU Execution

## Existing authority

`Recording`, `Job`, and `Attempt` remain authoritative for local lifecycle and
completion. `Job.status` remains `pending | processing | failed | complete`.
Remote state never marks a job complete directly.

## RemoteExecution

One row per `Attempt`.

| Field | Rules |
| --- | --- |
| `id` | Integer primary key |
| `attempt_id` | Unique foreign key to `attempts.id` |
| `provider` | Non-empty stable provider name, initially `runpod` |
| `idempotency_key` | Unique random value distinct from the local claim token |
| `external_job_id` | Nullable only while submission outcome is indeterminate; unique when present |
| `state` | `submitting`, `queued`, `running`, `succeeded`, `failed`, `cancelled`, `expired`, `indeterminate`, `abandoned` |
| `submitted_at` | Set when submission begins |
| `last_reconciled_at` | Updated after each authoritative status check |
| `reconcile_after` | Next bounded poll or owner-resolution threshold |
| `execution_timeout_ms` | Positive, initially `7200000` |
| `ttl_ms` | Greater than execution timeout, initially `10800000` |
| `result_reference` | Nullable object key/reference, never a credential or signed URL |
| `diagnostic` | Nullable bounded, secret-scrubbed text |
| `owner_resolution` | Nullable `wait` or `abandon_retry` |
| `resolved_at` | Nullable timestamp |

### State transitions

```text
submitting -> queued -> running -> succeeded
     |          |         |------> failed
     |          |         |------> cancelled
     |          |         |------> expired
     |          |         \------> indeterminate
     \---------------------------> indeterminate

indeterminate --owner wait--------> indeterminate
indeterminate --owner abandon-----> abandoned -> local failed -> retry -> new attempt
```

Unknown provider responses map to `indeterminate`. Automatic transitions out of
`indeterminate` are limited to later authoritative provider evidence; elapsed time
only enables the owner decision command.

## TransferObject

Tracks cleanup without persisting signed URLs or credentials.

| Field | Rules |
| --- | --- |
| `id` | Integer primary key |
| `remote_execution_id` | Foreign key to `remote_executions.id` |
| `direction` | `input` or `result` |
| `object_key` | Unique attempt-qualified bucket key |
| `sha256` | Expected content digest; result digest nullable until retrieved |
| `size_bytes` | Positive when known |
| `state` | `pending`, `uploaded`, `downloaded`, `deleted`, `cleanup_failed` |
| `retain_until` | Required only for failed-attempt diagnostics |
| `updated_at` | Last state change |

Signed URLs are generated on demand and never stored in SQLite. Successful local
publication requires both transfer objects to reach `deleted`, or records an
explicit cleanup failure without discarding the already verified transcript.

## Reconciliation order

For each processing serverless attempt:

1. Probe the known result object key. If present, download, verify digest and
   schema, and complete locally regardless of provider-status availability.
2. Otherwise query provider status.
3. For `queued` or `running`, atomically replace the expired claim token and lease
   on the existing job and attempt, then continue polling.
4. For terminal failure, record the mapped local failure.
5. Use `indeterminate` only if neither object nor provider evidence establishes an
   outcome. Do not run ordinary expired-claim recovery on an active or
   indeterminate remote execution.

## Relationships

```text
Recording 1--1 Job 1--N Attempt 1--0..1 RemoteExecution 1--2 TransferObject
```

SSH attempts have no `RemoteExecution`. Serverless attempts have exactly one.

## Migration

Initialization adds `remote_executions` and `transfer_objects` with `CREATE TABLE
IF NOT EXISTS` and indexes on external ID, state/reconcile time, and retention
cleanup time. No existing table is rebuilt and no existing row is changed.

## Invariants

- At most one remote execution exists per attempt.
- A local job cannot create a new attempt while its current remote execution is
  queued, running, or indeterminate.
- A queued/running remote execution has exactly one current local claim token; a
  restarting controller may atomically replace an expired token without creating
  another attempt or remote execution.
- Provider credentials, object-store secrets, model tokens, and signed URLs are
  absent from all rows.
- Result identity must match the recording digest before local publication.
- Object deletion occurs after successful local publication or after failed-run
  retention expiry; deletion is idempotent.
