# Vehicle archive and obligations (GC-018)

Archive hides a vehicle and pauses GearCargo's automatic activity. The archive
button and soft vehicle deletion have the same behavior. Insurance status,
coverage dates, auto-renew preferences, recurring taxes and parking schedules,
reminders, to-dos, service pointers, receipt files and notification state are kept.
Restoring changes only the vehicle's archive flags.

While archived, GearCargo excludes the vehicle from due/expiry feeds and calendar
subscriptions, reminder pushes and emails, mileage alerts, automatic insurance
renewals, and tax/parking generation. Recurrence date repair and duplicate-template
consolidation also pause. Existing consumable, warranty, document, service and
prediction jobs continue to exclude archived vehicles. Standalone reminders and
to-dos, with no vehicle, remain eligible.

Restoring resumes saved schedules. Overdue reminders can surface again, and
existing renewal/backfill rules can process dates that passed while archived.
Archiving does not suspend real-world contracts or stop real-world charges.
Use the existing insurance, tax and parking cancellation actions when obligations
actually end. Explicit cancellations remain cancelled after archive/restore.
Completing a recurring reminder or to-do requires restoring its vehicle first,
so completion cannot consume an obligation while its next occurrence is paused.

History remains readable through the normal record endpoints. Pending/due views
exclude archived vehicles. Calendar subscriptions omit archived reminders on the
next refresh, and bulk calendar sync skips archived vehicles. Previously copied
or downloaded events in an external calendar are not remotely deleted; review
those separately. Archive does not make any external cancellation request.

## Reviewing vehicles archived before this correction

Older archive behavior could cancel policies, replace their end dates with the
archive date, disable auto-renew, and clear recurring tax schedules. The original
values cannot be inferred reliably. Restoring a vehicle must not invent them or
reactivate a policy that was intentionally cancelled.

Run the read-only candidate inventory against the intended database:

```sh
cd backend
flask --app 'app.services.vehicle_archive:create_archive_review_app' check-archive-history --output archive-history-review.json
```

The minimal factory starts no jobs, recovery or administrator creation. The report
flags currently archived vehicles with policies cancelled on the archive date,
or taxes retaining a recurrence type but no enabled schedule. These signatures
are candidates for review, not proof of damage: intentional cancellations can
look the same. The report never edits rows or files. Vehicles already restored
have lost their archive timestamp and cannot be identified reliably this way.

Compare flagged records with source policies, bills and earlier backups. Correct
dates or recurrence explicitly after confirming the intended values. No database
migration or automatic repair is required or performed. Backups continue to retain
the stored archive state and obligation fields.

To roll back the application change, disable archive actions and scheduled writers
until the replacement release is ready: an older release can cancel obligations
again. Existing business data needs no reverse migration.
