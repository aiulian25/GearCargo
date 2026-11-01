# Portable personal backups (version 4.7)

A personal backup is a copy of vehicle data and portable preferences. It does not
replace an administrator's full database/media snapshot or the separately stored
keys needed for system recovery. Keep a verified system snapshot before destructive
maintenance. JSON/ZIP files are plaintext unless you enable optional backup
passphrase encryption (`.gcb`). See [protection and key recovery](BACKUP_ENCRYPTION.md).

## Included data

The explicit contract is `app/services/backup_schema.py`: `MODELS`, `FIELDS`,
`LINKS`, `EXCLUDED_COLUMNS`, `PREFERENCE_FIELDS` and `PREFERENCE_JSON_KEYS`.
It does not use frontend/display serializers. Its regression test fails when a
mapped column is added without an explicit backup decision.

- Vehicles: specifications, dimensions, units, purchase data, budget, maintenance
  intervals, display/archive state, stored analytics and timestamps.
- Fuel, service, repair, tax, parking and consumable records: all current stored
  fields, including zero/null values, currency, warranty details, recurrence and
  notification flags. Money/decimal quantities are JSON strings to avoid float
  rounding.
- Insurance: policy details, coverage, contacts and document/renewal relationships.
- Reminders: mileage/date, recurrence, completion, dismissal, snooze, translations,
  notification settings/state and source-service relationship. Remote CalDAV
  event IDs, credentials, versions and conflict snapshots are not portable.
- Todos, saved predictions and due-feed dismissals, including their relationships.
- Attachments: metadata, OCR text/state, expiry and notification state, VIN text,
  tags, timestamps, vehicle/entry links. Server disk paths are never copied.
- Language, timezone, theme, currency, units, date/country/location preferences,
  notification switches and seasonal-checklist progress/settings. These do not
  transfer notification-email identity, verification or consent.

IDs in the archive are source identities and relationship keys within their namespace. Every restored row belongs to the
signed-in destination account and uses destination database IDs. Tax-to-policy,
policy renewal/document, reminder-to-service, attachment, prediction and dismissal
references are remapped, including prediction metadata's vehicle and triggering
expense IDs. A fresh-account restore retains distinct records even
when their dates and amounts happen to match.
Attachment and insurance-document links must agree with their parent owner and
vehicle. Unambiguous omitted vehicles are derived during import; contradictory
links are rejected before mutation. Export also rejects inconsistent historical
links. See [Attachment parent consistency](ATTACHMENT_CONSISTENCY.md) for the
read-only review report and explicit repair options.

## Files and completeness

ZIP with files includes one member per attachment and each current vehicle photo.
An explicit media inventory records the archive member, source record, byte count
and SHA-256. The JSON data has its own manifest checksum. Missing source files
make a full ZIP export fail rather than silently produce an incomplete backup.
Full version-4 ZIPs with missing/corrupt declared members are rejected before
record import. File paths and MIME types are reconstructed, not trusted from the
source installation. Identical file content can share a destination file, while
same-named files with different content remain distinct.

JSON and ZIP with files disabled are **data-only** backups: attachment metadata,
OCR and links survive, but file downloads are unavailable until files are supplied
by replaying a full ZIP from the same source or through the document workflow. Vehicle photos are omitted. The backup and
restore result explicitly identify this limitation. A restored document with
missing bytes still has its metadata; attempting to download it returns the
existing file-not-found response.

## Account and server data intentionally excluded

Personal restore does not change account identity/profile/avatar history, passwords,
2FA/recovery material, permissions/limits, API keys, sessions, notification-email
consent/verification, push subscriptions, calendar credentials/feed tokens,
external-backup destinations, backup schedules/history, public report capabilities,
security/consent/delivery logs, pending deletion cleanup, server settings or shared fuel-price datasets.
Calendar delivery intents and deletion tombstones are also excluded: their
account, source and record identities belong to the original installation. Full
database backups include them. See [Calendar synchronization](CALENDAR_SYNC.md)
for reconciliation after restore and queue rollback limits.
Scheduled-job cursors and scheduled notification/upload intents are excluded
from personal backups and included in full database backups. Their ownership,
delivery and rollback semantics are described in [Scheduled jobs](SCHEDULER.md).
These are account/security/operational state, not portable vehicle records.
The unused legacy `FuelEntry.receipt_image` path is excluded; current receipt files
and metadata are Attachment records. Vehicle photos use the media inventory;
attachment disk paths and entry discriminators are reconstructed.

Portable preference keys are allowlisted. Unknown future preference keys and
credentials are never automatically exported from the open account JSON field.
On import the allowed preferences overwrite their corresponding destination values;
unrelated account/integration settings remain intact. No external requests are
made by restoration.

## Versions, legacy data and merge behavior

New exports use `version: "4.7"`, `format: "gearcargo-user"`. This version is
separate from the administrator system archive format. Version 1.0 (including
unversioned files) and 2.0 remain readable through an adapter. Unknown versions,
collections or missing required version-4 fields are rejected with a field/path
error instead of an apparently successful partial import. Export version 4 requires
a version-4-capable release to restore; retain old source archives when rolling back.

Older exports omitted consumables and many fields. They cannot be repaired by an
importer. Restore reports missing fields and unmatched references. Missing legacy
currency/distance units are stored as unknown (`NULL`), rather than guessed from
EUR/km defaults. Review those records explicitly; existing display code may still
show a fallback unit. Zero values are not replaced by aliases or defaults. Legacy
unmatched policies are skipped with a count and warning rather than reassigned.
Invalid required records fail validation; todos are no longer silently discarded.

Restoring into a fresh account is the lossless recovery path. Merging now uses
owner-scoped source identities, never date/amount equality. Version 4.2 includes
a source namespace and active source metadata. Preview distinguishes exact
replays, possible duplicates and changed-source conflicts. Explicit keep-existing
decisions preserve destination values; `replace` follows the same non-destructive
rules. See [Import identity and review](IMPORT_PROVENANCE.md) for source labels,
legacy limitations, migration, portable provenance and conflict handling.

Record import and file publication now use a durable recovery journal and one
outer database transaction. Interrupted restores recover the previous state or
retain a verified committed restore; unresolved recovery keeps data access in
maintenance. See [Restore recovery](RESTORE_RECOVERY.md) for storage requirements,
startup recovery, system archives and operator instructions. Checksums detect
accidental corruption, not authenticity or encryption. Existing ZIP size/path
safeguards remain.

## Restore result

All personal restore entry points (upload, stored backup and external ZIP) return
the existing `imported` object, extended with every supported collection count,
`source_version`, `format_version`, `media_included`, `skipped_records` and
structured `warnings` (`code`, `path`, `message`). The settings screen keeps this
result visible until the user explicitly refreshes. It reports legacy gaps,
missing files and retained merge matches instead of immediately reloading after
an unconditional success toast.

Version 4.1 adds nullable completion-origin links to reminders and todos so each
completed occurrence keeps at most one successor after recovery. Version 4.0
archives remain accepted with those links unknown. Historical duplicates are
preserved. Local record revisions and operation receipts are not portable: newly
restored records receive fresh revisions, and existing local receipts remain
bound to their original account. Full database backups include both. After a full
database rollback, suspend offline replay and review pending browser work before
resuming; a database snapshot cannot remember operations committed after it.

GC-019: version 4.3 adds nullable `purchase_currency`. Versions 4.0–4.2 remain readable; their missing purchase currency stays unknown and must be reviewed in Edit vehicle. Existing source identities with unknown currency remain replay-compatible. A rollback to an older application requires retaining the original older backup.

GC-021: version 4.4 adds reminder `repeat_mileage`, `recurrence_anchor_date` and `notification_state`. Per-channel outcomes survive personal restore so a successful push does not suppress a failed email retry, and restoring a reminder does not repeat its acknowledged channels. Dispatch claims expire after 30 minutes; they contain no transport credentials. Versions 4.0–4.3 remain readable. Their old `last_notified_at`/`mileage_notified` flags cannot prove delivery: reminders carrying those flags are treated conservatively as legacy delivery unknown, without automatically resending. An explicit reschedule or snooze opens a new notification cycle. Old recurring mileage reminders retain a null interval and require an explicit next threshold or an interval chosen by the owner. Restored dates and mileage stay in the vehicle's stored units. Keep an older compatible backup before rolling back an application or schema; older releases do not understand format 4.4 or its delivery state.


Version 4.5 adds tire sets, four permanent tire identities per set, fitment/rotation events and tread readings. Purchase expenses and receipts remain in their existing collections and are linked rather than copied. The importer remaps purchase/set/tire/vehicle IDs and validates chronology and position membership before writes. Versions 4.0–4.4 remain readable with empty tire collections. See [tire lifecycle and recovery](TIRES.md).


Version 4.6 adds workshop appointments, checklist/due-work links and completed visit expense links. Existing expenses and receipts remain single records. Restore remaps all links and validates time zones, states and owner-local relationships; formats 4.0–4.5 remain readable without newer collections. See [workshop visits](WORKSHOP_VISITS.md).

Version 4.7 adds selected statement batches, transactions and signed allocations. Restore validates relationships and exact balances; formats 4.0–4.6 remain readable without statement collections. Statement metadata never creates financial totals. Source deletion preserves expenses; previously saved archives retain their own copies. See [statement reconciliation](STATEMENT_RECONCILIATION.md).
