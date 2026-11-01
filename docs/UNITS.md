# Distance and fuel quantities (GC-015)

GearCargo stores odometers and distance thresholds in each vehicle's declared
`distance_unit`: `km` or `miles` (`mi` is a supported legacy alias). Fuel volume
is stored in **litres**, price in **currency per litre**, and consumption in
**L/100km**. A user preference changes display/input units, never stored history.

## Distance contract

- Vehicle current mileage, entry odometers, full-to-full `trip_distance`, service
  next-due mileage, reminder due mileage, predicted mileage, consumable lifespans
  and warranty distances all follow the vehicle unit. Historical names such as
  `warranty_km` and `expected_lifespan_km` do not imply an independent conversion.
- A vehicle with mileage, average trip distance, maintenance overrides or any
  expense/reminder/task/insurance/prediction history cannot switch distance
  units. The API returns **409 `DISTANCE_UNIT_LOCKED`**, and the edit form disables
  the switch with an explanation. An empty vehicle can choose its unit. Changing
  the equivalent `mi`/`miles` spelling is safe.
- This release chooses the audit's explicit blocking policy. It does **not**
  provide an in-place historical conversion tool. A future conversion must
  preview and atomically convert every distance and threshold together.
- Unknown legacy units remain unknown. Consumption cannot be derived from an
  unknown distance unit; source review is required before assigning one.
- One mile is exactly **1.609344 km**. LubeLogger conversion rounds an odometer to
  a whole target unit, half up, once at the import boundary. A km→miles→km round
  trip can differ by one kilometre because odometers have integer precision.

## Consumption and cost

Consumption uses complete full-to-full windows, including intermediate partial
fills. A full fill with odometer zero is a usable baseline. A missing odometer
accumulates known fuel until the next full fill with an odometer. First,
non-increasing or incomplete-volume windows produce no consumption estimate;
invalid historical measurements break the window instead of inventing fuel.

For example, 10 L over 100 miles is **6.2137119 L/100km**. Per-vehicle statistics,
fleet fuel statistics and health consumption weight each measured value by its
covered distance, with kilometres used across mixed-unit vehicles. They do not
average MPG values or invent estimates from partial-only histories. API
`fuel_efficiency`, `avg_efficiency` and `avg_consumption` are canonical L/100km;
`efficiency_unit` / `fuel_economy_unit` identify that contract.

Health `cost_per_km`, `total_distance_km` and CO₂/km use canonical kilometres, and
the health page labels that distance as km. Cost analytics `total_distance` and
`cost_per_distance_lifetime` use the returned vehicle `distance_unit`. Their
existing coverage and expense-inclusion rules remain: health uses measured
fuel windows; lifetime cost analytics uses its eligible odometer span. Due and
warranty comparisons use vehicle-unit readings and thresholds together.

## Fuel display and editing

The profile offers `liters`, `gallons_us` and `gallons_uk`. A US gallon is exactly
**3.785411784 L**; an imperial gallon is exactly **4.54609 L**. Explicit choices
win over country/currency and also select the matching MPG standard. Old
`gallons` preferences retain their existing regional fallback until the user
chooses a standard; no stored quantities are reinterpreted.

The fuel edit form retains the original quantities and omits unchanged fields
from its update. Notes-only saves therefore preserve litres, price per litre,
odometer, amount and total, even when the display was rounded to gallons. Zero,
refund prices and missing optional quantities remain distinct. A deliberate
quantity or price edit converts only that field; an automatically recalculated
total uses the unchanged counterpart's original canonical value and the same
storage scales (litres: two decimals, price per litre: three).

## Imports

LubeLogger multipart import accepts:

| Field | Values | Meaning |
|---|---|---|
| `source_volume_unit` | `liters`, `us_gallons`, `imperial_gallons` | Original fuel-volume standard |
| `source_distance_unit` | `km`, `miles` | Original odometer/threshold unit; overrides source settings |
| `distance_unit` | `km`, `miles` | Destination vehicle distance unit |

A source `UseMPG: false` declaration identifies metric values; `UseMPG: true`
identifies miles but **does not identify a gallon standard**. MPG fuel imports
require an explicit source-volume choice. Missing source settings require an
explicit source-distance choice when readings or reminder thresholds exist.
The UI always asks for the source volume and separately labels destination units.
Fuel litres, per-litre prices, odometers and reminder due mileage are converted;
original costs remain unchanged. Converted source measurements are retained in
notes/descriptions, and the import response records the chosen unit mapping.
Keep the original archive for full provenance.

Personal backup and LubeLogger merges reject attaching a history to an existing
matching vehicle with a different distance unit. Fuel imports (personal
JSON/ZIP, LubeLogger and CSV) recalculate derived metrics. Personal backups retain
source quantities, costs and timestamps; imported stale derived fuel values
are rebuilt. CSV odometers already use the target vehicle unit, while volume
and unit prices use litres. CSV is not a source-unit inference mechanism.

## Existing data: preview before applying

Previously misimported gallons cannot be identified or repaired from stored
numbers alone. Do **not** multiply existing litres based on vehicle unit or user
country. Preserve the original data and consult its source archive. The following
command rebuilds only derived fuel values and invalidates dependent health
caches; it does not fix uncertain source volume or relabel distance history.

Use the configured backend environment after the required migrations and backup
checks described in [data validation](DATA_VALIDATION.md) and
[restore recovery](RESTORE_RECOVERY.md). Stop normal application writers during
maintenance. Run the dedicated minimal factory, which does not start ordinary
recovery, schedulers, OCR or administrator initialization:

```sh
flask --app app.services.unit_rebuild:create_rebuild_app rebuild-unit-metrics --output /tmp/unit-preview.json
```

Review `changes`, `cache_invalidations`, `review_required` and the saved
`source_fingerprint`. Output files must be new; existing reports are never
reused or overwritten by a new invocation. Reports contain record identifiers
and old/new derived values, so keep them private. Preview performs no database
writes and also works on a database connection configured read-only.

After reviewing and preserving the preview, explicitly apply it:

```sh
flask --app app.services.unit_rebuild:create_rebuild_app rebuild-unit-metrics --apply --preview /tmp/unit-preview.json --output /tmp/unit-applied.json
flask --app app.services.unit_rebuild:create_rebuild_app rebuild-unit-metrics --output /tmp/unit-verification.json
```

Apply rechecks the fingerprint under locks and refuses a stale preview. It updates
only derived fuel fields, clears consumption/cost caches and the dependent health score, and increments
affected record revisions in one transaction. Odometers, litres, prices, amounts,
units, thresholds and source timestamps are untouched. Source corrections require
a separate explicit review; they are never guessed by this command.

The audit is written in `prepared` phase before commit, then atomically
marked `committed`/`applied: true` after commit. An audit-write failure before
commit rolls back database changes. A crash or final audit-write failure can leave
a `prepared` audit: retain it, generate a fresh preview, and compare its changes
before retrying. A prepared audit never claims the database committed. For
rollback, retain the original database backup and audit; do not run older unit
logic over repaired data. Rebuilding an unchanged corrected history is idempotent.

GC-034 removes the former 2,000-entry limit. Run the current preview/apply flow
after upgrading to repair **all** previously skipped derived values, including
histories already touched by an older version of this command. Version-1 previews
are rejected: create and review a fresh version-2 preview. Reports now include
`rebuild_scope: complete_fuel_history` and `entry_count`; a `committed` audit with
`applied: true`, followed by an unchanged verification preview, records completion.
Check `review_required` too: unknown units and malformed dates still require
source review. Source fuel quantities, odometers, prices and timestamps are not
converted by this repair.

### Long histories and ordinary writes

Complete recalculation traverses `(date, id)` order in pages of 256, carrying the
full-tank baseline and accumulated partial litres between pages. Pages flush in
one caller-owned transaction; there are no per-page commits. A failure rolls back
the entire operation and can be retried. Dates with multiple fills use ID order
consistently. Apply migration `gc034_fuel_history_index` for the owner/vehicle/date/ID
index supporting these lookups. Index creation can lock the entries table; plan
this upgrade with writers stopped. Downgrading removes only the index, not the
repaired values; older application code reintroduces the truncation.

Normal create/edit/delete requests recompute only the affected full-to-full
intervals. A date move repairs both its old and new intervals without visiting
every intervening record. Unrelated old values are **not** lazily repaired by the
next write: perform the explicit maintenance rebuild during upgrade. Imports
still rebuild their affected vehicles completely before committing.

Full historical maintenance stays in the existing operator-run CLI, outside an
HTTP request, rather than introducing a background job or a new pending API state.
This preserves atomic writes and the reviewed-preview/audit contract. The CLI's
complete snapshot and change report require memory/disk proportional to history
size; stop normal writers and allow sufficient resources/time. Ordinary writes
scale with the affected interval, and an unusually long partial-only interval or
a bulk import still takes proportional work. Batching bounds materialized ORM
pages, not total database work or a hard request deadline. This maintenance tool
does not run a data repair automatically at startup.

## Acceptance checks

Backend regressions: `python -m pytest -q tests/test_unit_semantics.py
tests/test_fuel_efficiency_chain.py tests/test_fuel_history_rebuild.py` (run on
both SQLite and PostgreSQL). Frontend regressions: `npm test --
src/__tests__/fuelUnits.test.js src/__tests__/fuelEditUnits.test.jsx`.

`frontend/browser-tests/unitSemantics.mjs` uses the existing disposable
`backend/tests/browser_queue_fixture.py` through a Unix socket. Set `GC_FRONTEND`
to a built frontend checkout, `GC_BACKEND_SOCKET` to that fixture,
`GC_BROWSER_OUTPUT` to a private result directory, and optional `PLAYWRIGHT_MODULE`
and `GC_CHROMIUM` paths, then run `node frontend/browser-tests/unitSemantics.mjs`.
Set `GC_LUBELOG_FIXTURE` to a synthetic two-record backup for the multipart import
check. The script exercises real forms, cookie authentication, repeated US/imperial
notes saves, the history unit lock, profile options and import selection.
Never point this fixture at a live database.
