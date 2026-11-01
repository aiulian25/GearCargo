# Offline write recovery (GC-009)

GC-011 defines the [private browser-data lifecycle](PRIVATE_BROWSER_DATA.md): logout/expiry purge private read caches while retaining unsent work in original-owner quarantine. Cached offline access is limited to 12 hours after online identity verification.

Supported vehicle, expense, reminder and todo record writes can be saved locally when a network request fails. The app reports a local save only after the worker acknowledges durable storage. Account/security actions, backups, generic uploads and action endpoints remain outside this queue. Expense receipts use the explicit parent-and-file workflow described in [RECEIPT_DRAFTS.md](RECEIPT_DRAFTS.md).

Open **Settings → Sync status → Review drafts** to inspect unsent changes. Export includes both paused and waiting drafts. Reviewing, exporting, discarding and resuming require the original account to be verified online, preserving GC-007's ownership checks.

- **401/403 or identity mismatch:** drafts pause. After a fresh sign-in to the same account, explicitly resume them. Automatic reconnect does not change their owner or sign-in generation.
- **409 revision conflict:** compare the saved record with the draft, edit fields, and queue the reviewed change. It uses the revision displayed in the comparison and a new operation key. Another concurrent edit pauses it again. Deleted records and reused operation keys require export/discard and manual review; they are not automatically overwritten or recreated.
- **400/422 validation:** correct the retained fields and queue a new attempt.
- **429, 408, 5xx or network failure:** keep the exact original payload/key for retry. Retry-After is respected with a 30-second minimum and a one-day maximum. Other rejections remain available for export/discard.
- **Over 24 hours old:** pause for review, resume or export. Time alone never deletes a draft.

The last-sync timestamp records a successful server acknowledgment, including an idempotent replay of an already committed operation. Registering a future sync event, an empty replay and failed requests do not advance it. Counts and timestamps survive reloads.

## Worker and storage contract

`GearCargoMutationIdentity` schema 2 adds a durable `pending` table alongside the existing identity state and quarantine. Queue metadata is version 3. A pending request stays in IndexedDB throughout its network attempt. Successful removal and the committed timestamp share one transaction; rejection moves the full sanitized request to quarantine transactionally. Recovery uses a row version to reject stale edits.

Native sync events and `FORCE_SYNC` call the same serialized replay implementation. A 20-second IndexedDB lease also excludes overlapping worker instances. A terminated worker can leave the lease until expiry; the next attempt can then resume. Fetches are bounded to three seconds, batches stop starting new requests after seven seconds, and page messages time out after fifteen seconds. A lost acknowledgment does not imply a lost draft.

Without Background Sync, manual sync, reconnect, restored sign-in, worker replacement and the open page's 30-second retry timer run the same implementation. Such a browser cannot wake this application after all its tabs close; reopen it online to continue. A browser with Background Sync can replay without an open application tab.

Activation lazily copies existing GC-008 Workbox entries before deleting their old rows, preserving payload, operation key, base revision and owner. Deterministic IDs make interrupted migration repeatable. Older unscoped entries stay quarantined and their security payloads are removed. Already quarantined entries without retry headers remain export/discard only. Downgrading to an older worker cannot process schema-2 pending drafts; re-upgrade to access them. Do not clear browser storage as a rollback step.

Storage remains local to this browser profile. Clearing site data, browser eviction, losing the device, or writes already lost before upgrading cannot be repaired by this feature. Export valuable drafts. Expense receipts now have a separate durable child workflow (GC-010); see [RECEIPT_DRAFTS.md](RECEIPT_DRAFTS.md). Vehicle photos and generic uploads remain outside this queue.

## Validation

From `frontend/`:

```sh
npm test -- --run
npm run lint
npm run build
```

The browser checks use Playwright, a built frontend, Chromium and the isolated `backend/tests/browser_queue_fixture.py` server. The fixture requires `GC_BROWSER_QUEUE_TEST=1`, synthetic secrets, disposable `/tmp` storage, and a Unix socket; never load it in production. Set `GC_FRONTEND`, `GC_BACKEND_SOCKET`, `PLAYWRIGHT_MODULE`, `GC_CHROMIUM` and a separate `GC_BROWSER_OUTPUT` directory, then run:

```sh
node frontend/browser-tests/offlineRecovery.mjs
node frontend/browser-tests/queueUpgrade.mjs
node frontend/browser-tests/mutationRetries.mjs
node frontend/browser-tests/queueIdentity.mjs
```

Use a fresh fixture database per script. `queueUpgrade.mjs` additionally needs `GC_BEFORE_FRONTEND` pointing to a built GC-008 frontend. The older unscoped migration scenario in `queueIdentity.mjs` uses a pre-GC-007 build in that variable. The recovery suite removes SyncManager from both the page and worker prototypes and asserts its absence. It uses real server revision conflicts and controlled transport/HTTP faults for the remaining failure matrix.
