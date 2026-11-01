# Scheduled jobs

`create_app()` does not launch scheduled work, OCR backfills or Ollama probes.
The container starts `python scheduler.py` as a separate s6 service after a
successful migration. Gunicorn uses the `web` role, Flask commands use `cli`,
and `python rq_worker.py` uses `worker`. Setting a role alone never starts jobs.
Gunicorn still preloads the app and disposes inherited database pools in workers.

For a source checkout, apply migrations before starting the dedicated process:

```bash
cd backend
flask --app app:create_app db upgrade
python scheduler.py
```

All processes must use the same database, encryption key and shared media/backup
paths. PostgreSQL is the production coordination backend. It requires a direct
connection or session pooling: transaction-pooling proxies cannot preserve the
session advisory locks. File-backed SQLite supports local development with a
shared database path and filesystem locks on one host; in-memory SQLite and
multi-host SQLite scheduling are unsupported.
Set `BACKUP_ENABLED=false` for SQLite development; the system archive builder
uses PostgreSQL's `pg_dump`.

## Deployment and recovery

The all-in-one image enables the designated scheduler by default.
`SCHEDULER_ENABLED=false` disables that service on an instance; keep one designated
scheduler enabled. Additional PostgreSQL scheduler processes safely contend for
the same job claims, but this does not make independently stored media or
embedded databases a shared deployment. Do not overlap old images that still
start an in-process scheduler with the new image during an upgrade.

`BACKUP_ENABLED=false` disables only daily/weekly system archives. Their UTC
schedule is unchanged: daily at 03:00 and Sunday at 03:30. Cron is no longer
activated. The documented manual archive command remains available, including
when scheduling is disabled:

```bash
docker compose exec gearcargo /etc/gearcargo/scripts/run-backup.sh manual
```

Each job has one durable cursor in `scheduled_job_runs`. The scheduler polls
every 15 seconds with at most four local job threads. A claim records its
occurrence, owner, fence and two-minute lease; a heartbeat renews every 15 seconds.
Lease expiry cannot displace a process that still holds its execution lock.
Database transactions validate ownership and check the lock before commit.
A replacement resumes the same occurrence after the owner disappears and its
lease expires. An indefinitely hung owner requires an operator to stop that
process; expiring its lease alone deliberately does not create overlapping work.

Failures retry the same occurrence after 1, 2, 4 and 8 minutes, then stop after
five attempts. Successful completion advances to the next future UTC schedule,
coalescing missed ticks rather than replaying the entire downtime. First use
seeds future schedules, plus delayed startup maintenance; it does not infer
historical deliveries. Deduplication maintenance runs once per installation.
Recurring generators, fuel refresh, OCR backfill and Ollama probing use the same
owner protocol instead of separate factory-startup threads.

## Delivery and visibility

Scheduled push/email notifications and external backup uploads are committed as
encrypted `scheduled_effects` intents with their domain changes. A unique
job/occurrence/effect key prevents regeneration on retry. A separate job delivers
up to 50 due effects per minute, with eight attempts, expiring delivery claims,
and backoff capped at one hour. Sent/cancelled receipts remain for deduplication;
their private payload is erased. Account deletion removes its effects.
The table also retains payload-free `recorded` generation receipts: an insurance
successor created by an occurrence cannot be renewed again by a retry of that
same occurrence, even if its short term is already expired. The next scheduled
occurrence may advance it normally. Email keys identify the report template,
so changes in rendered subjects do not turn a retry into another delivery.
Reminder push/email delivery retains its existing per-channel occurrence
receipts. Calendar delivery retains its own durable outbox and reconciliation.

Generator flags and report timestamps mean accepted into the durable queue;
transport delivery is tracked separately. Disabled accounts and changed email
destinations cancel pending effects. Delivery also rechecks report opt-outs and
whether a push notification's vehicle is still active. Failed transports retain encrypted payloads
until delivery, cancellation or account deletion. The deployment encryption key
must remain available when restoring pending work.

SMTP, Web Push and external upload services do not offer a common transactional
acknowledgement protocol. If a process loses its connection or dies after the
provider accepted a request but before recording success, a retry can repeat
that external request. Fan-out retries may also repeat an already accepted
subscription/destination. The database guarantees one logical intent, not
exactly-once delivery across those external systems. Backup archive filenames
are stable for an occurrence; publication is atomic and system archive retries
reuse an existing valid archive.

Inspect the durable state without starting a scheduler:

```bash
docker compose exec gearcargo flask scheduler-status
docker compose exec gearcargo flask scheduler-retry process_auto_renew_insurance
docker compose exec gearcargo flask scheduler-retry-deliveries
```

`scheduler-status` shows each job's enabled flag, status, attempts, occurrence,
next due time, last success, last error/time, lease and lag in seconds, plus
delivery counts by state. The same data is available to administrators at
`GET /api/admin/scheduler`. It excludes owner tokens and message payloads. An
empty job list before the first scheduler start is expected. Error codes are
sanitized; inspect application logs for diagnostics. Retry commands affect only
failed/retrying work and do not replay acknowledged deliveries. A successful
delivery-consumer tick can coexist with failed transport rows: inspect both.

Provider health and individual OCR outcomes remain in their health markers and
attachment state. A successful OCR backfill tick means a bounded page was
considered for admission, not that recognition finished. Dedicated OCR workers
also backfill images and PDFs independently of the scheduler, using the durable
queue and shared capacity described in [OCR operations](OCR_QUEUE.md).

The GC-027 `readiness_heartbeat` cursor records an actual scheduler poll every
15 seconds. `/health/ready` reports it stale after 60 seconds; see
[health checks](HEALTH_CHECKS.md). This is separate from individual job outcomes.

## Migration, backups and rollback

Migration `gc024_job_claims` follows `gc023_calendar_outbox` and creates two empty
operational tables. Personal exports exclude both; full database backups include
them. Restoring a full snapshot may recover pending/in-flight work as of that
snapshot, so account for the external acknowledgement ambiguity above. Shared
restore guards continue to pause scheduled work during restore.

Stop all schedulers before a schema/application rollback. Downgrading to
`gc023_calendar_outbox` drops both tables and permanently loses pending scheduled
deliveries, receipts and cursors. Preserve a full backup first, and drain or
explicitly account for pending work. Older images resume their former
single-instance scheduling limits; do not run old and new owners together.
