# Liveness and readiness

Use `GET /health/live` for restart-oriented liveness. It returns 200 with
`status: alive` when the web process can respond, without opening a browser
session, consulting Redis, running authentication/rate limits, or accessing the
database. A shared dependency outage should not restart healthy web processes.
Dockerfile and both Compose health checks use this endpoint.

Use `GET /health/ready` for load-balancer admission and deployment gates:

```bash
curl --fail --max-time 6 http://localhost:5000/health/ready
```

The CI boot gate checks this endpoint after migrations. Configure external
load balancers to require HTTP 200 here; keep their restart/liveness check on
`/health/live`. Docker Compose has only one health check, so its `healthy` status
alone is **not** a traffic-readiness guarantee.

`GET /health` retains its `healthy`, application/version and `redis_ok` fields for
older monitors. Its Redis boolean is the legacy **startup snapshot**, never a
current readiness signal. Move dependency alerts to `/health/ready`. All three
endpoints accept GET/HEAD, ignore cookies and return no-store JSON without
setting cookies. Other methods return 405.

## Readiness policy

| Component | Observed state | Effect |
|---|---|---|
| Database | Current connection/query, writable PostgreSQL primary, exact Alembic head | Failure/mismatch → 503, `not_ready` |
| Restore | Shared restore guard or unfinished recovery journal | Active maintenance → 503 |
| Redis browser sessions | Current PING when `SESSION_TYPE=redis` | Failure → 503; browser/CSRF state is required |
| Redis rate limiting | Current PING of the configured store when enabled | Failure → 503; never silently disable rate limiting |
| Optional JWT Redis cache | Current PING | Failure → 200, `degraded`, if required stores work; durable JWT checks remain mandatory |
| Scheduler | Successful `readiness_heartbeat` cursor within 60 seconds | Missing/stale → 200, `degraded` |
| OCR queue | Consumer timestamp for each configured slot within 120 seconds | Missing/stale → 200, `degraded`; saved work may be waiting |
| Optional RQ | Redis plus a bounded sample of up to eight worker heartbeats within 480 seconds | Missing/stale/unavailable → 200, `degraded` |
| Disabled scheduler/OCR, or in-process generic queue | Configuration reported explicitly | Does not degrade readiness |

`ready: true` accompanies HTTP 200; `status` distinguishes `ready` from
`degraded`. Ordinary application traffic remains useful while background work is
stalled, so those warnings do not remove the instance from service. Alert on
`degraded` and the component state as well as 503s. Heartbeats establish recent
consumer progress, not successful delivery of every email, backup or OCR job;
use the authenticated scheduler/OCR status views for individual failures.

Scheduler observation follows `SCHEDULER_ENABLED`; disabled instances report it
as disabled. When monitoring a shared deployment, monitor an instance configured
to expect the designated scheduler. OCR follows `OCR_WORKER_ENABLED` and
`OCR_MAX_CONCURRENCY`. Its consumer timestamp is distinct from decoder activity:
web image validation cannot make a stopped OCR consumer look healthy. The
120-second window covers the existing 90-second bounded OCR operation.
RQ sampling is deliberately bounded; a fresh worker outside the sample can yield
a conservative degraded result. A SimpleWorker busy for more than eight minutes
can also be reported stale until its next heartbeat. No queue entries, names,
worker identifiers, credentials, connection strings or user data are exposed.

## Bounds and recovery

Each web process caches the complete success/failure result for five seconds.
Only one probe runs at a time in that process; concurrent requests cannot launch
more probes or receive expired green results. While the first result is pending,
they get 503 with `checks.probe.status: checking`.

The probe runs in a disposable child with a four-second wall deadline, including
DNS/connect/read stalls. PostgreSQL also uses a two-second connect timeout,
750 ms statement timeout and 500 ms lock timeout; Redis uses 300 ms socket
connect/read timeouts. A timed-out child is killed and reaped. Probes use fresh,
unpooled database connections; SQLite is opened read-only. No tables are scanned:
only the schema-version rows, one scheduler cursor and two OCR slots are read.
RQ samples at most eight worker records. Poll no faster than every five seconds;
with four Gunicorn workers, there can be at most four concurrent probes.

Responses expose UTC `checked_at`, heartbeat `last_seen_at`, freshness thresholds,
`cache_seconds` and `probe_timeout_seconds`. Dependency outages/recovery are
reflected on the next check: allow five seconds of caching plus up to four
seconds for the new probe. A component sampled early in the previous probe can
add up to four seconds, for a conservative 13-second bound plus the monitor
poll interval and ordinary HTTP scheduling. Heartbeat failures additionally require
their documented stale window to expire. Timing is not a real-time SLA on an
overloaded host. Preloaded Gunicorn workers discard inherited cache/lock state.
No background probe thread starts during application creation.

## Upgrade and rollback

Apply migration `gc027_consumer_readiness` after `gc026_session_authority` before
starting new writers. It adds nullable `ocr_slots.consumer_seen_at`. Existing
rows remain unknown until a consumer polls; do not infer health from old decoder
timestamps. The new scheduler seeds its heartbeat cursor and polls every 15
seconds. During this warm-up, background components report degraded.

Personal exports already exclude OCR coordination rows. Full backups contain the
new column and follow the existing exact migration-revision restore contract.
No application data or sessions are invalidated by this migration. Stop new
writers before downgrading; the downgrade drops only the consumer timestamp.
Older `/health` clients keep working, but switch readiness consumers back as part
of an application rollback because older code has no `/health/ready` endpoint.
