# Permanent deletion and retryable cleanup

Vehicle hard deletion and administrator account deletion use one database
transaction for relational cleanup and `deletion_tasks`. Physical files and
Redis data are removed only after that transaction commits. A failed database
commit therefore leaves the original files intact. Soft deletion still archives
the vehicle and does not queue file deletion.

The existing foreign keys remain restrictive, except for the existing session
and report-share cascades. The service explicitly deletes owned rows in dependency
order. A reference from another account or vehicle stops deletion with HTTP 409
and a repair message; it is not silently cascaded. Ordinary successful responses
remain HTTP 200 with `Vehicle deleted` or `User deleted`, plus `cleanup.state`:

- `completed`: committed cleanup tasks finished, or a file was retained because
  another surviving record still owns it.
- `pending`: relational deletion committed; remaining cleanup will retry. The
  interface displays this distinction. A cleanup failure does not falsely report
  that the vehicle/account deletion failed.

A database connection failure during commit returns an error asking the user to
refresh before retrying: the result can be ambiguous. Committed tasks remain
recoverable independently of that HTTP response. There is no file deletion from
uncommitted tasks.

## Relationship policy

This inventory covers all current inbound foreign keys and the relevant logical
references. A regression test requires a policy review when new FKs are added.

| Records / references | Vehicle deletion | Account deletion |
|---|---|---|
| `vehicles.user_id` | Delete selected owned vehicle | Delete owned vehicles |
| `entries.user_id/vehicle_id`; fuel, service, repair, tax, parking, consumable subtype IDs | Delete all selected expenses, including base entries | Delete owned expenses and their subtypes |
| `tax_entries.insurance_policy_id` | Delete expense before its policy | Same |
| `attachments.user_id/vehicle_id/entry_id` | Delete vehicle and entry-linked documents; queue their files | Also delete unbound owned documents |
| `insurance_policies.user_id/vehicle_id/document_attachment_id/renewed_from_id` | Delete selected policies/renewals before documents | Delete owned policies; preserve foreign owners through restrictions |
| `reminders.user_id/vehicle_id/source_service_id` | Delete selected and source-service-linked reminders | Also delete unbound owned reminders |
| `todos.user_id/vehicle_id`; `prediction_alerts.user_id/vehicle_id` | Delete selected children | Delete owned children |
| `notification_logs.user_id/subscription_id/reminder_id/prediction_id/vehicle_id` | Delete logs for selected vehicle/reminders/predictions first | Also delete owned and owned-subscription logs |
| `due_dismissals.user_id` and logical `kind/ref_id` | Delete only matching owned occurrences | Delete all owned dismissals |
| `report_shares.user_id` and JSON `vehicle_ids` | Revoke shares explicitly selecting the deleted vehicle | Delete owned shares |
| `backups.user_id`, `backup_schedules.user_id` | Keep | Delete schedules/records; queue local archive files |
| `push_subscriptions.user_id`, `user_sessions.user_id`, `email_consent_logs.user_id`, `activity_logs.user_id` | Keep | Delete owned rows, including stored PII |
| Blocked IP/device `target_user_id`, `blocked_by_id`, `unblocked_by_id` | Keep | Detach links and scrub target email/descriptions; preserve the instance security block |
| Admin activity JSON `created_user_id`, `target_user_id`, `deleted_user_id` | Keep | Scrub target identifiers/email and description; keep the administrator's audit event |
| Vehicle photo; account avatar/history | Queue selected vehicle photo | Also queue avatars, including superseded files in the account avatar directory |
| Redis session/location/device/2FA and email attempt keys | Keep | Retry removal scoped to deleted account; never purge another account's keys |

The new account-deletion audit is committed with deletion and contains no deleted
email, name or account ID. Account deletion does not erase independent security
blocks, operator log files, externally exported calendars/backups or existing
administrator system snapshots. Those have their own retention/access policies;
deletion is not a claim of erasure from every historical copy.

## Cleanup and retention

Cleanup normally runs immediately after commit and retries every five minutes in
the existing scheduler. It is safe to retry after a process crash, including
between unlinking a file and acknowledging the task. A successful unlink is
synced to its directory before the task is removed. A missing file is an
idempotent success; unavailable storage retains the task.

Files are checked against their recorded SHA-256 before deletion. Changed files,
unsafe paths and symlinks require operator review. Live references preserve
shared files. Cleanup never renames or recursively removes a mounted media root.
The scheduler handles up to 100 tasks per run, giving less-attempted tasks
priority so a broken path cannot indefinitely starve new work.

There is **no quarantine or undo retention period**. Once deletion commits,
eligible files are purged as soon as cleanup succeeds. Failed tasks and original
files remain until the storage/Redis problem is repaired; they are not silently
discarded after a timeout. Pending account cleanup can temporarily contain the
email needed to remove Redis keys. Restrict access to the database/media and
monitor pending tasks until cleanup completes.

Run in the application's usual environment as its service user:

```sh
flask cleanup-deleted-files --limit 100
```

The command prints completed/pending counts and exits nonzero if work remains or
maintenance prevents access. Larger batches are supported up to 10,000. Repair
permissions, storage or Redis connectivity, then retry. For changed files or
reused account identifiers, review the task and surviving ownership first; do
not blindly delete the file or task. No failed task is a reason to retry the
original account/vehicle deletion without checking its committed state.

## Migration and deployment

Migration `gc003_deletion_outbox` follows `b7c8d9e0f1a2`. It checks every existing
foreign key for orphan rows before creating the outbox. Orphans stop migration
with a table/column/count diagnostic; no rows are automatically discarded. Repair
from verified data and run `flask db upgrade` again. Existing FK actions are not
widened. Downgrade refuses to drop a nonempty outbox; finish cleanup first.

All web/scheduler/queue processes must share the durable POSIX lock directory
introduced by [restore recovery](RESTORE_RECOVERY.md). Deletion and cleanup take
an exclusive lease before writes; busy requests return HTTP 503 for retry.
Stop old application versions and independent SQL/file writers during deployment
and deletion. Mounts must remain available at their configured paths. This
protocol cannot coordinate writers that bypass the application lease.

GC-003 covers permanent vehicle/account deletion. Standalone receipt/photo
replacement/deletion, general ownership validation (GC-017) and independent log
retention remain separate work. GC-004 makes migration/schema-sync failure stop
container startup; see [failed-upgrade recovery](../README.md#upgrade-stopped-by-a-migration-error).
