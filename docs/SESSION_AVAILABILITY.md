# Session validity during Redis failures

GC-026 makes `user_sessions` the authoritative record for JWT access authentication
(including the media decorator) and refresh. Every check requires an active user and a matching,
non-revoked session before its configured absolute deadline. Redis keys and JSON
payloads cannot authorize a session or extend that deadline. Missing, revoked or
expired credentials return 401; database verification failures return 503 with
`AUTH_UNAVAILABLE`, `Cache-Control: no-store` and `Retry-After: 5`.

Redis remains an optional JWT cache and additional denylist. A cache read error
falls through to mandatory database verification. A positive denylist result is
persisted as session revocation before rejection. Cache absence/eviction after
recovery no longer rejects a valid durable session; stale cache entries cannot
revive a revoked session. A database error is never interpreted as a cache miss.

Issuance must commit before a token is delivered. Refresh atomically revokes the
old session and creates its replacement, preserving the original absolute
expiry and offline identity. Concurrent refreshes of one session have one winner.
Single-device eviction and issuance commit together. Logout and bulk invalidation
commit revocation before best-effort Redis cleanup. Both password-reset paths
commit the password change with revocation, so a failed revocation cannot leave
the password changed while reporting a failed reset. Expired rows can be pruned;
recent revocation records remain available until expiry or daily cleanup.

## Browser proof and rate limiting

The browser's Flask/CSRF session store is separate from JWT sessions. If a Redis
browser-session read fails, return 503 before CSRF/authentication and preserve
the existing cookie. Do not invent an empty authenticated session. If its write
fails after a view runs, replace the response with 503 and withhold new cookies.
The durable operation may already have committed (for example, logout or refresh
revocation); no new credentials are delivered. A fresh sign-in may be required
when Redis recovers. Ordinary mutation retries retain their existing idempotency
contracts; 503 does not prove that an already-executed write was rolled back.

Clients whose requests do not need browser CSRF state can continue through the
JWT database policy if their other dependencies are available. A Redis-backed
rate limiter that loses its store also returns 503; it is not disabled to keep
requests flowing. Redis recovery never removes the database checks. If Redis
lost its stored CSRF state, obtain a new CSRF token before a browser mutation;
old proof correctly fails with 403. Authentication errors do not expose cache
keys, token strings or database connection details.

Existing short-lived HMAC media links retain their separate signature/expiry and
ownership checks; this change does not convert them into JWT sessions.

The legacy `/health` remains a startup/liveness response. Use `/health/ready`
for current dependencies and `/health/live` for restart checks; see
[health policy and bounds](HEALTH_CHECKS.md).

## Upgrade and rollback

Apply migration `gc026_session_authority` (file
`gc026_durable_session_authority.py`) after `gc025_attachment_processing` before
starting the new application. It invalidates all existing JWT sessions once.
Older code treated database writes as best effort, so an apparently valid row
could have a revocation recorded only in Redis. Those missing revocations cannot
be reconstructed safely if Redis has lost data. Requiring a fresh sign-in makes
the authority transition safe without trusting a lost denylist.

Stop all old web/auth writers, apply migrations, and start the new version on all
instances together. Do not mix versions: old writers do not provide the new
commit guarantees. Inform users that an upgrade requires sign-in and preserve
unsent offline drafts; the existing offline identity rules still apply.

The migration adds no columns/tables. Downgrade deliberately does not reactivate
revoked sessions. Rolling back application code restores its unsafe cache-first
behavior; it is not a security recovery. Preserve a backup before changing data.
The application rejects full backups with a different migration revision; older
snapshots need a controlled restore followed by this migration before serving
requests. A same-version full database restore can restore historical session
state like other security data; revoke sessions before reopening access if a
snapshot predates revocations. Personal exports do not include sessions.

Use the application's durable revocation helpers rather than deleting Redis
session keys or adding Redis-only blacklist entries as an administrative logout.
Removing cache data alone is no longer an authoritative revocation operation.
