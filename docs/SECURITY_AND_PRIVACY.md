# Security, deployment and privacy boundaries

This describes the current source checkout. It is an operator reference for the
README and the in-app privacy notice, not a legal certification or a guarantee
about an installed image. Tests below cover specific behavior; they do not
establish that every deployment or dependency is secure.

## Account and browser controls

| Behavior | Implementation and evidence | Limits / operator responsibility |
|---|---|---|
| Password hashing and optional TOTP/backup codes | [User model](../backend/app/models/user.py), [auth routes](../backend/app/routes/auth.py); [password regression](../backend/tests/test_password_security.py), [2FA lockouts](../backend/tests/test_2fa_lockout.py), [2FA disable](../backend/tests/test_2fa_disable.py) | Protect recovery channels and administrative access. The password-breach check sends the first five SHA-1 hash characters to Have I Been Pwned; errors fail open. It is not proof that a password is uncompromised. |
| Failed-login locks, IP/device rules and optional single-device sessions | [Auth routes](../backend/app/routes/auth.py), [blocked entities](../backend/app/models/blocked_entity.py); [account lockouts](../backend/tests/test_account_lockout.py), [Redis outage/session tests](../backend/tests/test_redis_auth_outages.py) | IP attribution depends on correct proxy trust. These checks are not a complete bot/abuse defense; notification mail and location detection also depend on configuration. |
| JWT purpose, durable revocation and non-sliding session deadline | [Auth `create_session`](../backend/app/routes/auth.py), [configuration](../backend/app/config.py); [token purpose](../backend/tests/test_token_purpose.py), [session authority](../backend/tests/test_redis_auth_outages.py) | The hard deadline uses `JWT_REFRESH_TOKEN_EXPIRES` (default 30 days), with a 48-hour fallback only if the configured value is not a `timedelta`. Refresh preserves that deadline. See [session availability](SESSION_AVAILABILITY.md). |
| Request rate limits, CSRF and response headers | [Factory](../backend/app/__init__.py), [cookie CSRF](../backend/app/services/cookie_csrf.py); [CSRF tests](../backend/tests/test_cookie_csrf.py), [Redis boundary tests](../backend/tests/test_redis_session_boundary.py) | Bundled Compose uses Redis-backed rate limits. Set exact origins and the real proxy depth; see [CSRF deployment](COOKIE_CSRF.md). Talisman headers and Secure cookies do not encrypt a directly reachable HTTP port. Production proxy headers/TLS must be checked on the actual deployment. |
| Startup secret checks | [Factory](../backend/app/__init__.py), [setup](../setup.sh), [Compose](../docker-compose.yml) | Production rejects missing/recognized placeholder application secrets. Short non-placeholder secrets and reused signing keys produce warnings, not universal rejection. Development/testing bypasses exist. Generate independent high-entropy values; do not treat the check as an entropy audit. |
| Activity/access/security logs | [Activity model](../backend/app/models/activity_log.py), [security audit](../backend/app/utils/security_audit.py), [HTTP logger](../backend/gearcargo_gunicorn_logger.py); [access canaries](../backend/tests/test_capability_access_logs.py), [audit IP tests](../backend/tests/test_security_audit_ip.py) | Logging is not an immutable or exhaustive ledger. Dedicated security logs retain PII. Review all proxy/collector sinks and historical logs under the [logging policy](../README.md#capability-safe-http-logs). |

## Field protection and backups

[Field encryption](../backend/app/utils/encryption.py) derives a key with
HKDF-SHA256 and uses Fernet: AES-128-CBC with HMAC-SHA256, as described by the
[cryptography implementation documentation](https://cryptography.io/en/latest/fernet/#implementation).
This protects selected fields, including authentication secrets, the custom
notification address, CalDAV credentials and saved automatic-backup passphrases.
The account email, ordinary vehicle data and uploaded files are not thereby
whole-database/file encrypted. The server holds decryption keys; this is not
end-to-end encryption. The normalized email SHA-256 lookup hash is not
anonymization. [Encryption tests](../backend/tests/test_encryption.py) cover
round trips, malformed ciphertext and lookup normalization.

[Backup encryption](BACKUP_ENCRYPTION.md) is a separate passphrase-based artifact
feature. JSON/ZIP/system tar.gz backups remain plaintext unless selected or
configured for encryption; `.gcb` artifacts use authenticated encryption. CSV
exports remain plaintext. Changing the setting or passphrase affects future
artifacts, not old copies. The runtime `ENCRYPTION_KEY` alone does not encrypt a
backup. Keep independent passphrase recovery copies and protect destination
storage. [Implementation](../backend/app/services/backup_encryption.py),
[backup routes](../backend/app/routes/backup.py), [system script](../scripts/docker-backup.sh)
and [round-trip/corruption/recovery tests](../backend/tests/test_backup_encryption.py)
provide the evidence; the guide explains unattended-key storage and restore limits.

## Container and processing boundaries

The [production Compose file](../docker-compose.yml) and
[development Compose file](../docker-compose.dev.yml) do **not** set `read_only`.
The root filesystem is writable. s6 starts as root, adjusts storage permissions
and starts services under dedicated users through the [service scripts](../docker/rootfs/etc/gearcargo/scripts).
Compose drops capabilities then adds the listed service-startup capabilities,
sets `no-new-privileges`, mounts persistent data and provides `/tmp` as tmpfs.
`/run` remains writable for the supervisor. These controls are not a validated
read-only-root deployment; none is supplied here.

Bundled PostgreSQL/Redis bind inside the container; only the app port is
published by Compose. That port defaults to **all host interfaces**. With a
same-host HTTPS proxy, set `APP_BIND_IP=127.0.0.1`. Other proxy topologies require
appropriate firewall/private-network access. Read [the Compose ports and mounts](../docker-compose.yml),
[PostgreSQL startup/shutdown](../docker/rootfs/etc/gearcargo/scripts/postgres-run.sh)
and [Redis startup](../docker/rootfs/etc/gearcargo/scripts/redis-run.sh).
A crash/forced stop can still require database recovery. Production Compose sets
no hard CPU/memory cap; development Compose has limits. Set capacity for your host.
No production start/stop, read-only-root boot, TLS or firewall test was performed
by this documentation correction.

Current [OCR coordination](../backend/app/services/ocr_queue.py) and
[decoder slots](../backend/app/services/decoder_slots.py) share up to two
processing slots across image validation, OCR and PDF extraction. The active
attachment queue defaults to 100 and can be configured downward. This requires
shared database/media, matching settings and supported locking: PostgreSQL direct
connections/session pooling, or same-host file-backed SQLite. Mixed old workers,
transaction pooling, in-memory or multi-host SQLite do not provide that contract.
Native CPU/address-space/time limits are **per child process**, not a total
container memory ceiling. Generic thread tasks remain bounded **per process**;
the optional RQ configuration does not control the OCR queue.
See [OCR operations](OCR_QUEUE.md), [decoder limits](IMAGE_PROCESSING_SECURITY.md),
[multi-process recovery/capacity tests](../backend/tests/test_ocr_job_recovery.py)
and [decoder tests](../backend/tests/test_image_decoder_limits.py).

## Network and proxy boundaries

CalDAV intentionally permits LAN/loopback HTTP endpoints and requires HTTPS for
public hosts. Its validator rejects known metadata names and certain IP literals.
Ollama accepts HTTP(S), including LAN/loopback; it rejects embedded credentials
and listed dangerous IP ranges. Neither validator is a complete DNS-resolution,
redirect or network-egress boundary. Use trusted destinations, authenticated TLS
where needed and an egress policy appropriate to your network. Do not describe
this as blocking all private/internal destinations.

Evidence: [CalDAV policy](../backend/app/services/calendar_service.py) and
[tests](../backend/tests/test_caldav_url_policy.py); [Ollama policy/transport](../backend/app/services/ollama.py)
and [URL tests](../backend/tests/test_ssrf_guard.py). External backup destinations
have a separate [resolve/validate/pin policy](../backend/app/routes/backup.py) and
[SSRF tests](../backend/tests/test_backup_ssrf.py); that stronger policy must not
be attributed to every integration.

The vehicle assistant queries owner-scoped records; its prompt/output checks
and optional topic classifier do not prove model truthfulness or confidentiality
at a remote provider. Prompts, selected vehicle context and receipt text may
leave this server for the configured Ollama endpoint. The application does not
control that endpoint's logs. Evidence: [chat routes](../backend/app/routes/vehicles.py),
[owner-isolation tests](../backend/tests/test_chat_data_isolation.py) and
[classifier tests](../backend/tests/test_chat_classifier.py). No external model,
CalDAV server or SMTP delivery was exercised for this documentation change.

## Public links

[Report shares](../backend/app/models/report_share.py) use random opaque bearer
tokens with only the hash stored, plus expiry/revocation checks. They are not
signed report documents. [Calendar feeds](../backend/app/routes/calendar_sync.py)
use purpose-checked JWTs expiring after 90 days; rotating the feed secret revokes
old links. [Media signatures](../backend/app/utils/__init__.py) constrain path or
attachment/user and expiry. Anyone obtaining a still-valid capability may use
its permitted access, and revocation cannot erase downloaded copies.
Evidence: [report tests](../backend/tests/test_report_shares.py), [feed validation](../backend/tests/test_calendar_feed.py),
[feed revocation](../backend/tests/test_calendar_feed_revocation.py) and
[signed URL tests](../backend/tests/test_signed_urls.py).

## Notification email

[Notification-email routes](../backend/app/routes/auth.py) require explicit consent
and verification of the optional custom address; verification tokens expire after
72 hours and are stored hashed. Removing that address clears its active fields
and records revocation. With ordinary notifications still enabled,
[`get_effective_notification_email`](../backend/app/models/user.py) falls back to
the account email. Use notification preferences or unsubscribe to opt out;
account recovery/verification and security messages are separate workflows.
[Token tests](../backend/tests/test_verification_token_hashing.py) exercise custom
address verification; [unsubscribe-token tests](../backend/tests/test_unsubscribe_token_hashing.py)
cover token storage/replay, not every email-client behavior.

[Consent rows](../backend/app/models/email_consent_log.py) contain action, email
hash, IP, user agent, text version and time. Normal routes append rows; the table
has no tamper-proof/immutable storage guarantee and account deletion removes its
rows. These controls do not establish GDPR compliance or legal certification.

[Email sending](../backend/app/services/email_service.py) records synchronous
`mail.send` outcomes. Five consecutive recorded failures to the custom address
clear its verified flag; a successful recorded send resets the counter. This is
not an asynchronous bounce webhook, inbox-delivery receipt or read receipt, and
fallback to account email may still occur. The legacy field name `bounce_count`
does not change that meaning.

Known implementation limits are intentionally documented, not fixed here:

- The unsubscribe route handles a public token-bearing **GET** link. The sender
  advertises a `List-Unsubscribe-Post` header, but the route has no POST handler;
  do not claim RFC 8058 one-click POST support.
- Verification endpoints check recent consent rows, but resends do not append a
  send-attempt record. This does not establish a strict three-sends-per-hour
  guarantee. General route limits still depend on limiter configuration.

## Data storage, access and retention

The [privacy notice](../frontend/src/components/settings/PrivacyPolicy.jsx) and
[EN/RO/ES copy](../frontend/src/i18n/translations.js) describe the built-in storage
and disclosure paths. The instance operator must supply their own contact,
retention periods and provider/deployment terms; the project support mailbox is
not automatically the controller/contact for every self-hosted instance.

| Data boundary | Implementation / evidence | Retention or disclosure limit |
|---|---|---|
| Account, vehicle, files and activity | [Models](../backend/app/models), [activity logs](../backend/app/models/activity_log.py), [attachment routes](../backend/app/routes/attachments.py) | Server/database/storage administrators can access records and keys. Ordinary vehicle data and files are not encrypted by field encryption. |
| Browser caches, profile, unsent forms/receipts | [Private storage](../frontend/src/utils/privateStorage.js), [storage contract](PRIVATE_BROWSER_DATA.md); [browser acceptance](../frontend/browser-tests/privateStorageLifecycle.mjs) | Logout clears private caches/profile but quarantines unsent payloads and pauses receipts for their original account. They are retained for recovery, not encrypted against access to the browser profile. Closed browsers cannot run timed deletion. |
| Enabled integrations | [Email](../backend/app/services/email_service.py), [push](../backend/app/routes/push.py), [CalDAV](../backend/app/services/calendar_service.py), [Ollama](../backend/app/services/ollama.py), [backup routes](../backend/app/routes/backup.py), [password checks](../backend/app/routes/auth.py) | Mail/push delivery data, calendar events, selected AI context and exports can reach configured providers. Password checks send a hash prefix; fuel/currency lookups also make external requests. No blanket “no third-party sharing” guarantee is made. |
| Personal exports | [Backup schema](../backend/app/services/backup_schema.py), [backup contract](USER_BACKUPS.md); [round-trip tests](../backend/tests/test_backup_full_roundtrip.py) | Supported vehicle data is exported; account secrets, operational/security records and all historical server data are not a complete personal export. Secure the resulting copies. |
| Vehicle/account deletion | [Administrator deletion route](../backend/app/routes/admin.py), [deletion service](../backend/app/services/deletion.py); [relational/file cleanup tests](../backend/tests/test_vehicle_delete_all_relations.py) | Account deletion is an administrator operation, not a self-service settings button. Live rows are removed transactionally; file/Redis cleanup is queued and may retry. Archive retains data. See [deletion recovery](DELETION_RECOVERY.md). |
| Historical and external copies | [Deletion exclusions](DELETION_RECOVERY.md#cleanup-and-retention), [cleanup jobs](../backend/app/services/__init__.py), [security logs](../backend/app/utils/security_audit.py) | Independent security blocks, operator logs, administrator system snapshots, external backups/calendars and downloads can survive deletion. Scheduler cleanup of old notification rows is not a universal retention policy. Operators must set retention/access rules for every store, archive and provider. |

## Upgrade boundary

These statements follow the current GC-025 OCR coordination, GC-028 optional
backup encryption and GC-032 capability-log changes. They must not be attributed
to earlier images: earlier OCR limits were per process; old backup artifacts are
not retroactively encrypted; old logs are not scrubbed by a code upgrade. Stop
old OCR workers and follow the linked migration guides. Check the installed
image/source revision instead of assuming a mutable image tag contains these
changes. This documentation update makes no runtime migration or deployment and
asserts no newly published release.
