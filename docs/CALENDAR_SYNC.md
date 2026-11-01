# Durable calendar synchronization

Saving, editing and deleting fuel, service, repair, tax, parking, insurance and
reminder records writes the desired calendar state in the same database
transaction. A failed or slow calendar provider does not run inside that request.
Completing or dismissing a reminder removes its remote event; a generated repeat
is a separate record with its own event. Removing the event date removes the
previous remote event. Existing formatting and date/alarm selection rules remain
unchanged.

The existing scheduler checks the queue every minute. Each batch attempts at most
50 records, at most five per destination, and stops processing a destination on
its first failure. Other destinations can still progress. Provider HTTP requests
have a 10-second timeout; discovery and an operation can involve several requests.
Retries use delays of 1, 2, 4, 8, 16, 32 and 60 minutes. After eight failed attempts
the change remains visible as failed until the owner retries or edits it.

Settings → Calendar Sync shows each source's waiting, retrying, failed, paused and
applied changes. These counts describe the latest state per source and record,
including acknowledged deletions; they are not the size of the remote calendar.
**Retry changes** retries that source's failed, delayed or paused work.
**Sync all** queues reconciliation of current active records plus outstanding
retries. It returns immediately after the local transaction, without waiting for
the provider. Connection tests and calendar discovery remain explicit remote
operations. Status persists across restarts and does not require Redis.

## Delivery and lifecycle guarantees

- The historical UID remains `gearcargo-{type}-{id}@gearcargo.local`. Before an
  upsert, the worker searches that UID, updates its existing provider resource in
  place, and removes duplicate resources only after the update succeeds. Retries
  after an ambiguous provider response reuse the UID. Unrelated events are left
  alone. GearCargo owns the contents of events with these UIDs.
- Edits coalesce to the newest desired state. Database compare-and-swap claims
  prevent simultaneous consumers from normally delivering the same generation.
  A claim expires after five minutes if a consumer dies. An edit or deletion
  during delivery remains pending after the older generation is acknowledged.
  A late completion from an expired consumer requeues newer desired state,
  including a deletion, even if another consumer already acknowledged it.
  This is retryable, at-least-once delivery, not a distributed transaction with
  the provider. Another pass reconciles an interrupted delivery.
- Deletions retain a tombstone until the provider acknowledges absence, including
  hard vehicle deletion. Tombstones remain as acknowledged delivery records.
  Deleting the account removes its queue and stops future synchronization; it
  does not erase the former account's remote calendar.
- Archiving preserves historical remote events and pauses automatic upserts.
  Restoring a vehicle resumes reconciliation. Disabling a source or the global
  calendar switch pauses its delivery. Saving enabled settings or choosing retry
  resumes it; retry cannot bypass an archived vehicle or inactive account.
- Removing a source, or changing its URL, username, provider or selected calendar,
  cancels work for the former destination. It does not delete that calendar's
  existing events. A request already in flight cannot be recalled. Password-only
  changes retain queue identity. Credentials remain encrypted in account settings
  and are read only when claiming work; jobs contain no credentials or URLs.
  Provider failures shown in status and application logs use generic messages.

## Migration, operation and rollback

Run the normal `flask db upgrade` before application startup. Migration
`gc023_calendar_outbox` adds one table and two indexes. It does not contact any
provider or automatically rewrite existing calendars. Existing events reconcile
on the next edit or an explicit Sync all. Records deleted before this migration
have no recoverable tombstone and require manual remote cleanup.

The normal scheduler processes the queue. With the application's usual Flask and
database environment, `flask process-calendar-outbox --limit 50` processes one
bounded batch and can safely run alongside another consumer. The limit accepts
1–500; per-destination limits and claims still apply. Scheduler ownership for
other jobs is unchanged (GC-024 remains separate).

Personal backups exclude this account/destination-bound delivery state. Full
database backups include it. Database restore cannot roll back a remote calendar;
after recovery, review the current destinations and explicitly synchronize to
reconcile restored live records. Events created after the backup and no longer
represented locally may require manual cleanup.

Before downgrading, stop consumers, retain a full database backup and resolve or
export outstanding queue/tombstone state. The migration downgrade drops the
queue, losing pending deliveries. Older application versions restore the former
best-effort calendar behavior; a downgrade cannot undo remote writes.
