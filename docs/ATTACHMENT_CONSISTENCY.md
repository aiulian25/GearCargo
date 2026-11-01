# Attachment parent consistency (GC-017)

An expense receipt has the same owner and vehicle as its expense. An insurance
document has the same owner and vehicle as every policy referencing it. A vehicle
document belongs to that vehicle's owner. An upload with no parent and no vehicle
is valid while a receipt draft is being completed.

Upload and link requests derive an omitted vehicle from the selected parent.
Conflicting supplied vehicles and foreign parents are rejected before file or
metadata changes. Parent IDs for insurance are explicitly distinguished from
expense IDs; their numeric values are not interchangeable.

## Relinking and historical repair

Attachment updates validate the complete proposed relationship before changing
fields. An expense receipt can move with an explicit `entry_id` and matching
`vehicle_id` in the same PUT request. Sending only a conflicting parent preserves
the existing conflict response. A metadata edit cannot silently change owners.

After reviewing the source receipt and its records, an authorized owner can:

- Correct `vehicle_id` to the existing expense's vehicle.
- Explicitly move `entry_id` and `vehicle_id` together to another owned expense.
- Clear an incorrect expense link with `entry_id: null`, retaining the document.
- Explicitly clear owned insurance links with `insurance_id: null` before or while
  moving the document. Links from another account cannot be cleared implicitly.

Use the existing `/api/attachments/<id>` GET/PUT interface, authentication and
mutation protocol (`If-Match` and a fresh idempotency key). Reload the document
before reviewing/editing it. Conflicts preserve metadata, file bytes and revision;
successful changes advance revisions and retain the existing receipt file.

## Read-only inventory

Run the minimal CLI factory against the intended database:

```sh
cd backend
flask --app 'app.services.attachment_consistency:create_consistency_app' check-attachment-links --output attachment-link-review.json
```

The report contains attachment/parent/vehicle identifiers and reasons such as a
missing record, owner mismatch or vehicle mismatch. It does not include receipt
bytes, OCR contents or file paths. The factory does not start recovery, scheduled
jobs, OCR or administrator creation. The command does not change rows or files.
It can inspect historical data without a schema migration.

Review each finding against source documents before choosing a correction. A
missing vehicle on an entry-linked historical receipt can be reported even when
its intended parent is clear. A non-null contradictory vehicle or different owner
must never be guessed. There is no automatic reassignment or deletion. Cross-owner
or missing-parent history may require an administrator's separately reviewed
maintenance operation or recovery from a known backup. Run the report again after
any maintenance.

## Enforcement and recovery

The shared `attachment_consistency` service validates ORM relationship writes
and parent moves after SQLAlchemy synchronizes relationship IDs, before commit.
PostgreSQL uses a transaction advisory lock to serialize parent moves and receipt
links. SQLite serializes writes through its normal database transaction. Related
bulk ORM inserts and updates to relationship fields are rejected because they
bypass relationship flush validation; metadata-only bulk updates remain allowed.
Use ordinary model objects. Stage all sides of a deliberate move in
one flush (`session.no_autoflush` while assembling changes).

This is an application transaction constraint, not a new database foreign-key
migration. Existing malformed records remain available for review. Direct Engine
SQL, legacy bulk-session APIs and independent database writers are administrative
boundaries and can bypass model guards; they must use the inventory and an
explicitly reviewed maintenance plan. No existing data is rewritten on deployment.

Portable backup preflight derives absent vehicles from unambiguous parents and
rejects contradictory source links. Destination relationships are checked again
after restore ID mapping, including provenance-based merges. Import failures roll
back records, provenance and staged files through the existing recovery journal.
Export rejects inconsistent relationship graphs instead of producing an apparently
valid personal backup with wrong links. LubeLogger and receipt/OCR handoff use the
same import/model and upload/link paths.

Vehicle deletion refuses contradictory receipt links before scheduling file
cleanup. Historical omitted vehicle IDs remain deletable through their known
parent when every known parent is the selected vehicle. Correctly moved receipts
survive deletion of their former vehicle. Account deletion retains its existing
owned-data and foreign-reference protections. No new file deletion behavior is
introduced.

To roll back the application change, retain the review report and stop relationship
writers; older releases can reintroduce inconsistent links. Files and historical
rows are not automatically changed by this implementation.
