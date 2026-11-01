# Receipt drafts (GC-010)

GC-011's [private browser-data lifecycle](PRIVATE_BROWSER_DATA.md) preserves submitted receipt drafts in original-owner quarantine across logout/expiry. Unsaved shared receipts and private read caches are purged; anonymous shares are never handed to the next account.

Fuel, service, repair, tax, parking, insurance and consumable forms now save the expense operation and selected receipt together in one IndexedDB transaction before sending either. Saving requires an active service worker and the originating account's local identity. If storage fails, the form remains open and no expense request is queued. A selected file is not locally durable until Save is acknowledged.

The parent keeps its GC-008 operation key. After its idempotent server response supplies the parent ID, the worker uploads the retained Blob with a separate persisted key and links it with another persisted key and an attachment revision. The original file remains local until the server confirms the intended parent. OCR and expense submission share the upload key, including when the OCR response is lost or its callback is late. Insurance linking uses an explicit `insurance_id`, never an expense ID with the same number.

If the expense succeeds but attachment work does not, the form announces the pending receipt and Settings → Sync status shows **Receipts waiting to attach**. The list updates as each stage changes. It offers retry, original-file download and explicit removal of the local draft. Removal stops attachment retries; it does not delete the expense or an already uploaded file, which remains accessible in vehicle documents.

- Upload 413 and other permanent rejections retain the file for download/retry after correcting the cause.
- Network/5xx/429 failures preserve operation keys and retry with backoff. Lost successful responses replay the original result instead of creating another file.
- Link 409 retains both the Blob and uploaded attachment ID. A known revision conflict requires explicit review before a new link intent. Conflicting parents and unknown operation conflicts cannot be overwritten automatically.
- Sign-in changes pause receipt replay. Another account cannot upload, view, export or discard the original account's draft. Review requires live verification of the original account; authentication failures require a fresh sign-in before resuming.
- Parent validation/conflict recovery remains in the existing unsent-changes panel. A receipt follows its repaired parent's successful result. Moving the expense to another vehicle requires explicitly removing its local receipt first.

Limits are 10 MiB per file, 50 MiB of local receipt files and 100 receipt drafts per browser profile. The transaction checks the total before committing, and actual browser quota errors abort both writes. After 24 hours, automatic receipt replay pauses for review; files are never deleted merely because they are old. Download important files before clearing site data. Browser eviction and device loss cannot be prevented by this local store.

The store is `GearCargoMutationIdentity` schema 3, with a `receipts` table. Existing identity, pending and quarantine records are preserved. Old queued expenses never stored their missing files; upgrading cannot reconstruct those receipts, which must be selected again. Older workers cannot process the new receipt store; re-upgrade without clearing site data. Deploy the updated backend before the new frontend, especially for explicit insurance links.

Upload and link routes now reject mismatched parent/vehicle pairs before modifying metadata or creating files, and derive an omitted vehicle from its verified parent. Historical/imported mismatches remain GC-017 work. The separate todo/reminder document flows and vehicle photos are outside this expense-receipt rollout.

Validation uses `npm test -- --run`, `npm run lint`, `npm run build`, focused backend `tests/test_receipt_draft_links.py` plus retry/identity/upload/backup/deletion regressions on SQLite and PostgreSQL, and `frontend/browser-tests/receiptRecovery.mjs`. The browser runner uses the isolated `backend/tests/browser_queue_fixture.py` described in `OFFLINE_RECOVERY.md`, a built frontend, and a disposable persistent Chromium profile. It shuts down/reopens the browser after an offline form save and checks original bytes, exactly-once linking, HTTP faults, account switching, OCR handoff and atomic quota failure. Never load the test fixture in production.
