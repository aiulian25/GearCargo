# Record retries and revisions (GC-008)

The retry contract applies to create/update/delete on vehicles, fuel, services,
repairs, taxes, parking, consumables, insurance, reminders, todos and attachments.
It also applies to reminder completion/snooze, todo completion/reopening,
recurring tax/parking/insurance cancellation, vehicle archive/restore and mileage.
Permanent vehicle deletion continues to use the separate online deletion recovery
workflow. Account, admin, import, backup, photo, OCR and recommendation actions
are not generic replayable record writes.

## Request contract

| Header | Meaning |
| --- | --- |
| `Idempotency-Key` | One random UUID per intent, created **before** its first attempt. Accepted syntax: 16–128 ASCII letters, digits, `_` or `-`. |
| `X-GearCargo-Mutation-Version: 1` | Requires an operation key and, for an existing record, `If-Match`. |
| `If-Match: "123"` | The positive integer `revision` returned with the record the editor displayed. Do not fetch a newer revision just to make a save pass. |

Keys are unique per authenticated account, across participating routes. The
fingerprint covers method, path, query, base revision and canonical JSON; uploads
include form fields, filenames, MIME types and content hashes. A retry with the
same key and fingerprint returns the original HTTP status and body, with
`Idempotent-Replay: true`. A changed request with that key returns 409
`OPERATION_KEY_REUSED`. Validation failures and failed transactions do not consume
keys. The receipt and record changes commit in one transaction. Concurrent keys
are arbitrated by a database unique constraint, not a process-local cache.

A stale edit or delete returns 409 `REVISION_CONFLICT`, `current_revision`, and
the current owned record in `current` (or null for missing/unowned records).
The client must review and reload, then start a new intent. It must not silently
replace `If-Match` or retry with the latest revision. ORM writes advance revisions,
including joined expense subtype fields. New records start from a random 52-bit
incarnation revision so reusing an ID during recovery does not accept an old
editor's revision. Migrated rows start at 1.

Legacy online clients without protocol/identity headers still work, but creates
without an operation key are **not idempotent**, and edits without `If-Match` do
not provide stale-editor protection. Account-bound offline requests must use the
new protocol; an old worker stripping its headers receives 428. Deploy the schema
and backend before the new frontend, and require users to reload old clients.

## Browser and recurrence behavior

Forms retain their operation key on failed submission and preserve the revision
they loaded. Token refresh retries keep the same headers. The worker stores and
replays those exact headers with account identity. Queue metadata version 2 is
required; older items are paused, never assigned a new operation ID after an
uncertain commit. Revision/key conflicts are paused for owner-only export/review
or explicit discard. No automatic overwrite or merge is performed. General
rejected-write recovery and the manual-sync fallback remain GC-009.

Actions and binary uploads remain outside the offline queue allowlist. Online
uploads preserve a key for retries of the same selected file until success. File
activation and OCR/calendar dispatch occur after the database commit; replaying
a receipt does not dispatch them again. These are still best-effort follow-up
effects: recovery after process death between commit and dispatch belongs to the
durable job/outbox work in GC-023–025. Attachment deletion uses the existing
durable file-cleanup outbox, committed with its receipt.

Reminder and todo completion lock the parent and advance only an incomplete
record. Each new successor records a unique nullable `completed_from_id`.
Historical duplicates remain untouched and unlinked. Reopening and completing
a todo cannot create a second existing successor for that occurrence.

## Recovery and retention

Personal backup 4.1 carries recurrence-origin links and accepts 4.0 archives with
unknown origins. It excludes local revisions and operation receipts. Imported
records get fresh revisions; destination receipts retain their original account
scope. Merge conflicts with an existing successor are rejected with an explicit
field error and rolled back. Receipts describe historical outcomes, so replaying
one after a restore or deletion does not imply its old record still exists.

Full database backups include receipts. After rolling back a full database,
suspend replay and review pending browser work: a snapshot cannot remember later
commits. Receipts are retained without automatic expiry, including after record
deletion, and removed with account deletion. They contain historical response
data; include the table in storage/privacy retention planning. Do not prune it
while clients can retry those operations. Downgrade refuses to drop a nonempty
receipt table. Preserve the database and pending browser work before an explicit
rollback decision; no migration automatically deletes duplicate user records.

## Validation

Run `python -m pytest -q tests/test_mutation_retries.py tests/test_offline_identity.py`
from `backend`, then the full suite on SQLite and with `TEST_DATABASE_URL` pointing
to a **disposable PostgreSQL database**. Fixtures drop all tables. The focused
suite covers response loss, key reuse/scope, concurrent requests, joined subtype
edits, completion, delete/retry, upload rollback, migration rollback guards, and
personal restore/import. Concurrency tests intentionally require PostgreSQL.

From `frontend`, run `npm test`, `npm run lint`, and `npm run build`.
`browser-tests/mutationRetries.mjs` launches Chromium against the built worker and
the opt-in `backend/tests/browser_queue_fixture.py` Flask application. Run that
fixture only with `GC_BROWSER_QUEUE_TEST=1`, disposable storage, and a Unix socket.
It creates synthetic accounts and exposes test-only inspection/deletion routes;
never serve it on a production or publicly reachable endpoint.

The browser runner requires `GC_FRONTEND` (absolute frontend directory),
`GC_BACKEND_SOCKET`, and optionally `GC_BROWSER_OUTPUT`, `GC_CHROMIUM` and
`PLAYWRIGHT_MODULE`. It starts a loopback proxy, drops an expense response **after
commit**, dispatches a real worker sync, retries manually, then submits two real
vehicle-edit forms in separate tabs and checks visible conflict/draft retention.
It also verifies owner-only retention of a conflicting offline update. The
separate `queueIdentity.mjs` runner checks account isolation after the protocol
change; start a fresh disposable backend for each runner.
