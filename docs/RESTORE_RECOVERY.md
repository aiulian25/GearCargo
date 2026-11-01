# Restore recovery and maintenance

Personal JSON/ZIP restores and administrator system restores use journal version
1. The journal lives in `BACKUP_FOLDER/.restore` by default. Set
`RESTORE_STATE_FOLDER` only when all web workers, scheduler processes, queue
workers and the container backup scheduler share that same durable directory.
It must be writable by the application and separate from both media roots.
Do not put it in `/tmp`. Linux/POSIX file locking, hard links, durable `fsync` and
same-filesystem rename are required; storage must honor these operations.

## What happens during a restore

The application obtains an exclusive file lock before a restore request performs
any authentication or data writes. Existing requests and background operations
hold shared locks. A busy application returns HTTP 503 with `Retry-After: 5`;
retry when the current operations finish. Other data requests are temporarily
blocked during cutover. Static application files and the minimal
`/api/backup/recovery-status` endpoint remain available. The status endpoint
exposes only maintenance state and phase, not account data or filesystem paths.

1. Validate the archive, supported version, references and supplied checksums.
2. Write a private, durable journal and stage files on their destination volume.
3. Apply database changes and publish staged media while holding the lock.
4. Commit a unique `app_settings` marker in the **same database transaction**.
5. Verify published media, record the outcome durably, then remove staging and
   rollback copies. Marker cleanup is optional after the journal is removed.

A filesystem rename and a database commit are **not intrinsically atomic**.
The journal plus commit marker resolves interruption at that boundary. If the
marker is absent, recovery undoes publication and preserves the earlier database.
If the marker is present, recovery verifies and keeps the completed new state.
An ambiguous database connection failure does not blindly delete published files.
Recovery uses a database transaction lock before deciding the commit outcome.

For personal restores, files are never overwritten. Existing identical file bytes
can be reused; conflicting names get separate destinations. Metadata and portable
preferences participate in the same SQL transaction. `import_backup_data` is now
an internal, non-committing helper; callers must own transaction completion.

## System restore requirements

System restore requires PostgreSQL CLI tools (`pg_dump`, `psql`, `createdb`,
`dropdb`) and permission to create/drop a temporary validation database and
terminate its restore SQL session. The standard embedded PostgreSQL deployment
provides these tools. An external PostgreSQL role without these permissions fails
before live cutover; provide the required operator access before retrying.

The incoming SQL is first applied to a generated temporary database. Its table and
column shapes and Alembic revisions must match the installation. The previous
live database is saved as a private compressed dump before any cutover. Both media
trees are staged, retaining previous contents in rollback areas on their own
volumes. Mounted root directories stay in place: the operation switches their
contents, not the mount points. Overlapping media/journal roots are rejected.

SQL uses `psql --single-transaction -v ON_ERROR_STOP=1 -f -`; the commit marker is
part of that transaction. The journal records the SQL child's process identity
before sending SQL. Recovery stops an orphaned child/server session before
resolving its transaction. If SQL did not commit, the previous dump and **both**
media trees are restored. Old copies remain until verification succeeds.

New application-generated system archives use version 3.1 with SHA-256 for the
compressed database and each media file. Historical version 3.0 archives,
including existing container-script backups, remain readable with an explicit
missing-checksum warning; their SQL/schema is still staged and validated. Unknown
versions, unsupported members and mismatched checksums fail before live changes.
Checksums detect corruption, not authenticity. Restore only trusted administrator
SQL archives. Personal backups keep their separate version-4 format.

## If a restore is interrupted

The settings screen retains a failed-restore result. `rolled_back` means recovery
restored the prior state; `recovery_required` means the journal/copies are retained
and data access stays blocked. Do not retry imports or delete recovery files to
bypass this gate. A lost browser connection alone is not evidence of rollback.

Startup attempts recovery before application background work. The container also
runs recovery before schema migrations, and its scheduled backup wrapper will not
capture data while restoration/recovery is in progress. After fixing a full disk,
unavailable volume or database connection, restart the application or run this
command in the application's normal environment as its service user:

```sh
flask recover-restores
```

The command reports `idle`, `rolled_back` or `completed` on success and exits
nonzero when recovery remains unresolved. After it succeeds, refresh the browser
and review the recovered data before retrying an import. Recovery is idempotent, including after
partial cleanup. Preserve `active.json`, its operation directory and all referenced
`.gc-restore-*` areas until the command succeeds. These can contain sensitive
previous database/media data; retain their private permissions.

If the journal version is unsupported or recovery storage is damaged, keep the
application in maintenance and retain the evidence for operator recovery from the
verified snapshots. Do not manually remove `active.json` to reopen writes.

## Operational boundaries

All application processes sharing the database/media must share the lock/journal
storage. Stop independent SQL clients, manual file writers and older application
versions before restoring; they do not participate in this protocol. Mount loss,
hardware corruption or storage that ignores durability guarantees can require
operator repair. A restart during an active restore must use the same storage and
compatible application schema. Allow space for staged new media and retained old
media/database copies before starting.

The request remains synchronous; the progress display polls server phases. This
does not add a general durable job queue. Existing-account import matching remains
GC-016; encrypted envelopes are documented below. System restore resource budgets
are described in the next section. Failed migrations or opted-in schema synchronization now stop container
startup (GC-004); see [failed-upgrade recovery](../README.md#upgrade-stopped-by-a-migration-error).

## System restore resource budgets

GC-035 validates tar headers, payloads, checksums and the complete nested SQL gzip
before creating even the temporary validation database. It reads tar and SQL in
64 KiB chunks. Tar member metadata is processed incrementally; manifest parsing
is separately capped. Path traversal, links, special/sparse files, recursive
extension headers and global PAX metadata are rejected. Local PAX and GNU long
names from normal system exports remain supported. Archive versions 3.0/3.1 and
optional authenticated `.gcb` envelopes use the same checks.

Set these environment variables on every application/recovery worker and restart
it. Values are positive integers; bytes are binary units. Zero, negatives and
`unlimited` are rejected. Defaults:

| Variable | Default | Applies to |
|---|---:|---|
| `SYSTEM_RESTORE_MAX_MEMBERS` | `100000` | All tar headers, including directories and extension headers |
| `SYSTEM_RESTORE_MAX_MEMBER_BYTES` | `2147483648` (2 GiB) | Each file's declared expanded size, including compressed SQL |
| `SYSTEM_RESTORE_MAX_ARCHIVE_BYTES` | `8589934592` (8 GiB) | Expanded outer tar, including headers, padding and trailing gzip streams |
| `SYSTEM_RESTORE_MAX_SQL_BYTES` | `8589934592` (8 GiB) | Expanded incoming SQL and the previous database snapshot, separately |
| `SYSTEM_RESTORE_MAX_MANIFEST_BYTES` | `8388608` (8 MiB) | Manifest and each permitted tar extension payload |
| `SYSTEM_RESTORE_MAX_PROCESS_BYTES` | `536870912` (512 MiB) | Address-space ceiling for each `psql`/rollback `pg_dump` child (Linux `prlimit`) |
| `SYSTEM_RESTORE_MIN_FREE_BYTES` | `536870912` (512 MiB) | Free space retained on upload, journal and destination-media filesystems |
| `SYSTEM_RESTORE_TIMEOUT_SECONDS` | `1800` (30 minutes) | Import preparation, validation and cutover processing deadline |

Disk checks run before declared payload extraction and on each file-copy chunk.
Before publication, each media destination must have room for its complete new
copy plus the reserve. Existing media remains in place until publication and is
retained for rollback afterward. The previous database snapshot is streamed to
gzip on disk, rather than held in memory. SQL uses a nonblocking pipe, with no
unbounded stdout/stderr capture, a child memory ceiling and a deadline. PostgreSQL
statement/connect timeouts also limit waiting; the journal still tracks the SQL
child before any input and resolves commit versus rollback after interruption.
Recovery starts a **fresh** bounded attempt, so an expired import deadline does
not prevent rollback. Failed recovery retains its evidence and maintenance gate.

For a larger legitimate archive:

1. Use a separate, adequately sized installation with the same schema and trusted
   runtime field-encryption keys. Keep the original backup intact.
2. Provision space for the uploaded compressed archive, authenticated plaintext
   and its named copy when encrypted, extracted media and compressed SQL, a
   compressed snapshot of the existing database, and another copy of new media
   on each destination filesystem. Add the reserve to each filesystem's required
   capacity. The upload/authentication files use `TMPDIR` (default `/tmp`); the
   recovery journal uses persistent `RESTORE_STATE_FOLDER`. Do not put the journal
   on temporary storage.
3. Separately provision the PostgreSQL server for the validation database,
   restored tables/indexes and transaction/WAL overhead. Client filesystem checks
   cannot measure a remote database server's free disk. These trusted-admin SQL
   dumps are not sandboxed SQL; archive budgets do not limit server-side query
   allocations. Use appropriate PostgreSQL/container resource controls too.
4. Increase only the finite limits needed for measured archive sizes, file count,
   schema complexity and expected runtime. Check the HTTP upload limit
   (`MAX_UPLOAD_SIZE_MB`) and proxy/worker timeout too; increasing a restore budget
   does not raise those independent limits. Trial the restore on that installation
   before production recovery. Keep all path/type, checksum and schema checks.

The deadline is checked between bounded reads, copies and validation steps;
blocked filesystem calls/fsync cannot be forcibly interrupted by it. Recovery and
cleanup may outlast the import deadline to preserve atomicity. Reserve checks are
best effort against concurrent unrelated disk use, not filesystem quotas. A low
space or budget error names the limiting setting and leaves live state unchanged
when caught before cutover; cutover failures use the journal's rollback protocol.
This change limits restores; system **export** sizing is unchanged.

## Encrypted archives

GC-028 adds `.gcb` envelopes. All import entry points authenticate them before
invoking this recovery protocol. See [backup passphrases and offline recovery](BACKUP_ENCRYPTION.md).
Full database recovery still needs its original runtime field-encryption keys.
