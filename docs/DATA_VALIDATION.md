# Business-record validation (GC-014)

Vehicle, expense, insurance, reminder and to-do writes share field validation at
request entry and before persistence. CSV, personal JSON/ZIP backups, and
LubeLogger imports use the same domain rules. A rejected API write returns HTTP
400 with `error`, `message_key`, and (when identifiable) `field`. Invalid writes
roll back their record changes, related mileage changes and operation receipt.
CSV retains its existing per-row result contract: valid rows import and invalid
rows appear in `errors`. Personal backups reject invalid records before restore. Exports continue to
preserve historical domain values so they can be backed up before review.

## Client contract

- Numbers may be JSON numbers or decimal strings with a dot separator. Booleans,
  nonfinite values (`NaN`, infinity), overflow, and comma-decimal strings are
  rejected. Clients must convert localized input explicitly before submission;
  the server does not guess whether a comma is a decimal or thousands separator.
- Integer fields accept whole values such as `12000` or `"12000.0"`. Fractions
  are rejected rather than truncated. Storage is bounded to signed 32-bit
  integers; odometers, dimensions, durations and warranty distances are
  nonnegative. Quantities, recurrence counts and expected lifespans are positive.
  Years are 1–9999 and percentage/health fields are 0–100.
- Decimal values use `Decimal` and round half up to the mapped column's scale
  before storage. Money usually has two decimals, fuel unit prices have three,
  and tank capacities have one. Both the input and rounded result must fit the
  column precision. Backups require exact precision and never round source data.
- Negative ledger totals, fuel unit prices, labor/parts costs and insurance premiums explicitly
  represent refunds or credits. Fuel quantities, purchase prices,
  budgets, coverage and deductibles cannot be negative. This introduces no new
  ledger type or change to report aggregation.
- Text must be a string within its column length. Enumerated values must be
  recognized application options (including supported historical spellings).
  JSON booleans must be actual `true`/`false`; CSV also accepts its documented
  true/false, yes/no, on/off and 1/0 spellings.
- Currency codes must belong to the checked-in ISO 4217 snapshot in
  `backend/app/utils/entryparse.py`; unknown/test markers are excluded. Ordinary
  input is uppercased. Recognition does not promise an exchange rate. Archive
  values must already use canonical uppercase codes. Legacy missing currencies
  and distance units remain unknown; imports do not infer them.
- Existing nullable-field and date-default behavior remains. `null`/empty
  optional numeric fields can clear a value. Zero odometers remain zero.

Clients relying on silent integer truncation, permissive boolean coercion,
unknown enum values, oversized text or nonfinite numbers must correct their
payloads. Preserve a rejected import file and review the field/path diagnostic;
do not edit away uncertain source values just to make an import pass.

## Read-only repair report

Before planning repairs, preserve the original database and files using the
GC-001/GC-002 backup and recovery workflow. Run in the configured backend
application environment:

```sh
flask --app app.services.domain_scan:create_scan_app validate-records --output /tmp/gearcargo-repair-report.json
```

This dedicated CLI factory connects only the database. It does not start the
normal application's recovery, scheduler, OCR or administrator-initialization
work. The command scans all accounts' business records and reports table, record ID,
field, reason and required manual review. It does not include raw field contents,
update records, clamp amounts, infer currencies, or perform repairs. Keep the
report private because record identifiers refer to account data. Missing currency
and distance-unit values are reported for review, not assigned defaults.

The scanner reads raw database values so malformed historical SQLite numerics
can be reported without failing in the ORM's numeric decoder. Missing tables/columns are listed separately in `schema_gaps`, allowing older
installations to scan the fields they actually store. A deployment's
live database must be scanned in that deployment; an isolated regression scan
is not a production-data audit. System disaster recovery retains its existing
source-preserving behavior; run this report after restoring historical data.
