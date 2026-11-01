# Receipt processing

GC-025 stores OCR intent and its result on the attachment. Uploads, manual retries,
admin backfills, startup recovery and PDF extraction use the same database queue.
Web processes never launch OCR threads. The `ocr-1` and `ocr-2` s6 services start
after successful migrations, independently of the scheduler and optional RQ.

For a source checkout, apply migrations and start each worker in a separate
process with the same database, encryption key and shared upload paths:

```bash
cd backend
flask --app app:create_app db upgrade
python ocr_worker.py --slot 1
# In another terminal:
python ocr_worker.py --slot 2
```

## Capacity and recovery

| Setting | Default | Bounds / behavior |
|---|---|---|
| `OCR_WORKER_ENABLED` | `true` | Disables queue admission and consumers when false |
| `OCR_MAX_CONCURRENCY` | `2` | Clamped to 1–2; deployment-wide processing slots |
| `OCR_MAX_PENDING` | `100` | Clamped to 1–100; queued + running + retrying attachments |

Slots use PostgreSQL session advisory locks and durable leases. Direct connections
or session pooling are required; transaction-pooling proxies are unsupported.
Replicas must share the database and media, and use the same capacity settings.
File-backed SQLite uses OS locks and supports one host with a shared database
path. In-memory/multi-host SQLite is unsupported. Drain in-flight work before
reducing the slot count. Keep at least one consumer for each configured slot.

Row 0 in `ocr_slots` serializes admission; rows 1 and 2 reserve execution capacity.
The attachment records `queued`, `running`, `retry`, `failed`, `done` or
`unavailable`, attempts, generation, owner, lease, next attempt and sanitized error.
Repeated requests for active work reuse its intent. Results must match the claim's
owner and generation. Retrying a terminal result starts a new generation.

Workers poll every two seconds and admit at most 100 legacy attachments per page
every 30 seconds. Finished legacy results remain finished. PDFs are included;
only legacy unprocessed rows without a state are automatically backfilled.
Overflow/failed rows require a manual retry, avoiding endless automatic retry of
poisoned files. There is no in-memory waiting thread per attachment.

An OCR/PDF child has a 90-second independent wall deadline, 60-second CPU limit,
768 MiB address-space limit, 10 MiB input limit and 10,000-character output limit.
Image decoding retains its stricter GC-005 limits, including 512 MiB address
space and 12-second wall time. These are per-process bounds, not a measurement of
total container RSS; size the host for two OCR parents, bounded decoder/native
children and the normal web/database services. Child processes are killed when
their supervisor dies. Processing uses Linux resource and parent-death controls.

A 180-second lease prevents reuse after database lock loss until the bounded
child must have exited. A live execution lock cannot be stolen by lease expiry.
Recovery resumes the same attachment after worker loss; attempts stop after
three failures. Processing errors retry after 30 then 60 seconds. Missing files
fail immediately. A committed upload left as a `.tmp` file is activated by its
recovering worker. Restore guards pause work during full restore.

PDF support extracts embedded text from the first ten pages; scanned PDFs with
no text can finish successfully without extracted text. It does not rasterize
PDF pages or add optical recognition to scanned PDFs.

## User and operator status

`GET /api/attachments/<id>/ocr` and attachment responses include `ocr_state`,
`ocr_attempts`, `ocr_error` and `ocr_next_attempt_at`, alongside the existing
`ocr_processed`, text and `has_text` fields. Existing upload `ocr_status: pending`
remains for accepted work. The UI distinguishes waiting, scanning, retrying,
failed and unavailable states and offers re-scan for images and PDFs.

Queue overflow or disabled/unavailable admission preserves an accepted upload
and ordinary expense data. Its scan status explains failure. Explicit re-scan
returns 429 for a full queue or 503 for unavailable admission. Required image
validation happens before acceptance: if both processing slots are busy, an
image upload returns 503 and the user must retry uploading. Unvalidated images
are never saved merely because OCR capacity is unavailable.

`GET /api/admin/ocr` returns state counts, configured limits, and each slot's last
seen time and lease. Tokens, paths and OCR content are omitted. A stopped consumer
leaves work queued and its last-seen time stale; a database write alone does not
prove a consumer is healthy. Worker exceptions appear in application logs.

`POST /api/admin/maintenance/ocr-backfill` considers one bounded page. The
`force=true` query parameter includes completed/failed attachments; `after_id`
continues from `next_after_id`. A full
queue returns no admitted work. Do not loop force backfills from ID zero if you
intend to scan each attachment only once.

OCR does not depend on `TASK_QUEUE_BACKEND`. Importable legacy RQ OCR functions
only admit work into this queue. Generic thread tasks now have two workers and
100 waiting positions per process; explicitly configured unavailable RQ raises
an error without falling back to threads.

GC-027 adds `consumer_seen_at`, written only by an OCR consumer, separately from
the shared decoder/activity timestamp. `/health/ready` reports missing/stale
consumers after 120 seconds; see [health checks](HEALTH_CHECKS.md).

## Migration and rollback

Migration `gc025_attachment_processing` follows `gc024_job_claims`. It adds
attachment processing fields and seeds three coordination rows. Existing
`ocr_processed=true` rows become `done` without being reprocessed. Pending legacy
rows are admitted gradually. Personal backups exclude operational fields and
slots while retaining finished OCR text; full database backups include them.

Stop old web/RQ/scheduler processes before upgrading; old images bypass the new
capacity guarantees. Do not mix old and new images. Before rollback, stop all
consumers and web writers and preserve a full backup. Downgrading to
`gc024_job_claims` removes queue metadata and slots but retains OCR text and the
processed flag. Queued/retry intent is lost; the old image resumes its former
per-process limits. No deployment or automatic rollback is performed by this
change.
