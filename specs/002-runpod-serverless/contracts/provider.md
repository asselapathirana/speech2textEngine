# Provider Contract

## Provider-neutral operations

The controller uses a provider adapter with these semantic operations:

```text
submit(request, idempotency_key) -> submission
status(external_job_id) -> remote_status
cancel(external_job_id) -> remote_status
```

`submit` receives recording identity, input/result presigned URLs, and execution
policy. It returns either a durable external job ID and normalized state, or an
indeterminate submission outcome. No provider credential or raw provider response
crosses this boundary.

`remote_status.state` is one of:

```text
queued | running | succeeded | failed | cancelled | expired | indeterminate
```

For success it may include a bounded result manifest. Diagnostics are bounded and
secret-scrubbed. Unknown or malformed provider responses become `indeterminate`.

## Runpod mapping

| Runpod status | Shared state |
| --- | --- |
| `IN_QUEUE` | `queued` |
| `IN_PROGRESS` | `running` |
| `COMPLETED` | `succeeded` |
| `FAILED` | `failed` |
| `CANCELLED` | `cancelled` |
| `TIMED_OUT` | `expired` |
| Missing, unknown, or uncertain response | `indeterminate` |

The adapter uses asynchronous `/run`, `/status/{job_id}`, and
`/cancel/{job_id}` operations. HTTP 429 and transient 5xx responses use bounded
backoff without creating another job.

## Idempotency and uncertain submission

Each remote execution has a separate random idempotency key included in the request
payload; the local claim token is never transmitted.
If the HTTP outcome does not establish whether Runpod accepted the request, the
adapter returns `indeterminate` with no automatic second submission. After the
configured resolution deadline, the owner uses `resolve-remote` to continue
waiting or explicitly abandon the execution and enable a fresh local retry.

## Result-first recovery

Before mapping a missing, expired, or unavailable provider status to
`indeterminate`, reconciliation probes the persisted result object key. A present
canonical JSON document whose recording digest and schema validate is normalized
as `succeeded`. Only absence or invalidity of that object followed by inconclusive
provider status produces `indeterminate`.
