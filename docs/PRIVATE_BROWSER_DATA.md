# Private browser data (GC-011)

Logout, failed session renewal, a definitive session-expired response and account changes share one asynchronous cleanup boundary. Identity is suspended first. Pending record writes move atomically to account-bound quarantine and receipt files pause for their original owner; then private caches, cached profiles, share-target files, location and account markers are removed. A failed purge prevents the next login request from changing cookies. Other open tabs lock their authenticated UI. Late responses cannot populate a new account's caches or profile, or trigger expiry handling against its new session.

## Storage inventory

| Storage | Policy |
|---|---|
| Private API responses and `/api/`, `/media/`, `/uploads/` media | Cache names include owner, session generation and binding revision. Page reads require a matching tab binding. Checks before/after reads and writes reject old responses; private network responses use `no-store` for the browser HTTP cache. |
| Cached profile | Stored with its identity/revision in `GearCargoMutationIdentity.state`, in an atomic transaction. Removed on suspension. The old `GearCargoDB.settings.user` record is never trusted and is deleted. |
| Shared receipts | A signed-in share uses the current scoped namespace and is read once through the worker. A share received while locked/signed out is discarded; the login page asks the user to sign in and share again. No anonymous file passes to the next account. |
| Unsent record and receipt drafts | Retained under GC-007/009/010's original-owner recovery contract. Logout removes active pending requests, quarantines their payloads and pauses receipt Blobs. Review/export/resume/removal require online verification of the original account. Retention is intentional; these files are not encrypted against access to the browser profile itself. |
| Local account/location markers | `auth_session`, `userEmail`, `username`, `gearcargo_user_location` and `seasonalBannerDismissed` are cleared. Late geolocation callbacks are scoped/cancelled. |
| Navigation handoffs | New receipt/expense prefills live in memory; browser history carries only an opaque reference. Account changes discard handoffs, and legacy unscoped prefills are ignored. Reloading before saving loses this unsaved handoff; save the expense to use durable receipt storage. |
| App assets and presentation preferences | Precached app shell, scripts/styles, fonts, public images, theme and language remain available offline. Public branding and token-authorized shared report reads remain network-only and never enter private caches. |

## Offline access

An online identity verification unlocks cached private reads for at most **12 hours**. This is an intentional local offline session, not proof that a server session is still valid. A network failure may restore the matching profile within that window; the browser's `navigator.onLine` flag alone is not authoritative. An HTTP authentication failure cannot restore it. Offline writes retain the existing account/retry checks.

After the window ends, the next private read, app startup or open-page lifetime check locks access and purges private data. Open pages check at 30-second intervals. A closed browser cannot execute a timed physical purge; the next application/worker activity performs it. Background reminder refresh uses the same cache and expiry guards. A fresh online verification is required to unlock again.

## Upgrade and compatibility

The repeatable first-use migration deletes legacy `api-cache`, `media-cache`, `images` and `share-target-cache` buckets and private legacy settings. Clearing all of `images` is deliberate: older workers stored signed uploads there. Public images refill in `public-images-v1`. Existing queued work and receipt files are preserved, and the existing IndexedDB schema is reused.

The updated application and worker must run together. An older worker cannot acknowledge the new private-storage protocol; reload/update online rather than clearing site data and losing drafts. Downgrading restores older privacy behavior and is not a privacy-safe rollback. Previously saved browser-history entries, downloads and files exported outside the application cannot all be erased programmatically; the application no longer consumes legacy private navigation state. Server cookies and signed URLs remain subject to server-side expiry/revocation; this change governs local application storage.

## Validation

Run `npm test -- --run`, `npm run lint` and `npm run build` from `frontend`. Focused tests are `privateStorageLifecycle.test.js`, `privateNavigation.test.js`, `apiInterceptor.test.js` and `mutationTransport.test.js`.

`frontend/browser-tests/privateStorageLifecycle.mjs` uses the existing disposable Flask fixture in `backend/tests/browser_queue_fixture.py`. Set `GC_FRONTEND` to the built frontend directory, `GC_BACKEND_SOCKET` to that fixture's Unix socket, and optionally `GC_BROWSER_OUTPUT`, `PLAYWRIGHT_MODULE` and `GC_CHROMIUM`, then run `node frontend/browser-tests/privateStorageLifecycle.mjs`. Never load the test fixture in production.

The browser matrix inspects real Cache Storage/IndexedDB after migration, logout, expiry and account switching. It checks anonymous and signed-in shares, a held response across a switch, another open tab, the production app's offline reload, quarantined receipt preservation, public route compatibility and cleanup failure before login. Existing `queueIdentity.mjs` and `receiptRecovery.mjs` provide account/receipt regression checks.
