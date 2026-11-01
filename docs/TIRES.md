# Tire sets and seasonal history

Open a vehicle's **Consumables → Tire sets**. Create a summer, winter or all-season
set with four permanent identifiers, initially assigned to front left, front
right, rear left and rear right. Keep these identifiers with the physical tires:
rotation changes positions, not identities. Sets belong to one vehicle.

Link a purchase already recorded in Consumables, or use **Record a purchase with
receipt** and link it afterward. The existing expense and its attachments remain
the only financial record. Tire sets do not add another expense. Purchase links
can be changed or cleared; deleting the expense clears the link.

Use **Install**, **Rotate**, and **Remove and store** with a date and the vehicle's
odometer unit. Review all four positions before saving. A vehicle can have only
one set installed at a time. Remove the current set before installing another.
Dates and known odometers must form a chronological vehicle history. Events in
the same calendar day use their recorded order. Future events are not supported.
The history lets you correct dates/odometers or undo a set's latest event; the
complete vehicle timeline must still be valid. Tire identifiers are permanent.

Distance includes only installed segments. Removal pauses accumulation, even
while the vehicle's odometer increases on another set. The current vehicle
odometer supplies the end of an open segment; update it in the vehicle when
needed. Missing or inconsistent endpoints produce an explicit **additional
distance unknown** indication, not a guessed distance. Known closed segments
remain visible. Kilometres and miles retain the vehicle's declared unit; unit
changes are locked once a tire set exists.

An optional rotation interval uses distance driven on this set, across seasonal
storage periods. Only a rotation resets that interval. An unknown interval stays
unknown until a known rotation gives a new starting point. Rotation alerts are
shown only while the set is installed. **Create maintenance reminder** opens the
existing reminder form with the rotation type and a current mileage threshold
when available; the owner chooses notification channels/date/recurrence there.
That reminder is an independent commitment and does not automatically change
when the set is removed or rotated.

Record tread depth against a permanent tire identifier, using millimetres or
32nds of an inch (one 32nd = 0.79375 mm). History retains each reading's original
unit and measurement date. The optional personal tread threshold has its own
selected unit; the latest reading per tire is compared after conversion. No
universal legal threshold or roadworthiness assessment is applied. Readings may
be taken while a set is stored. Incorrect readings can be deleted and re-entered.

The dashboard's existing due feed includes your rotation/tread alerts, with
vehicle links and measurement dates. Archived vehicles retain history but have
no tire alerts or tire writes. Empty sets can be deleted; sets with history are
retained. Permanent vehicle/account deletion includes all tire records.

## Offline and concurrent changes

Tread observations on existing sets use the account-bound offline queue with an
operation ID and the set revision shown in the form. The app announces local
storage only after the service worker acknowledges it. Replaying the same
operation cannot create a second reading/event. A changed set revision pauses a
queued reading for review; it is not silently rebased. Use the existing offline
review/export/discard tools. Set creation, fitments, corrections and deletions
remain online. Unsaved forms use the existing leave-page protection.

## Persistence and recovery

Migration `feature_tires_lifecycle` follows `gc034_fuel_history_index` and creates
`tire_sets`, `tires`, `tire_fitments`, and `tread_readings`, with owner/vehicle
indexes, required parent references, unique identifiers per set and nonnegative
reading/odometer constraints. Apply migrations through the normal container
startup or `flask db upgrade`; no migration has been applied to production by
this implementation task. Downgrading this migration removes tire history, so
keep a verified backup before rolling back.

Portable backup version **4.5** includes all four collections and remaps their
purchase/vehicle/set/tire references. It validates links, four distinct identities,
positions and the full fitment chronology before restore. Versions 4.0–4.4 remain
readable with empty tire collections; earlier JSON/ZIP adapters remain available.
An older application cannot restore version 4.5. System archives include the new
tables and still require a matching database schema. Existing GC-002 recovery,
GC-008 mutation receipts and GC-016 import provenance apply.

The API is `/api/tire-sets`: list with `vehicle_id`, create, get/update/delete a
set, append `/events` or `/readings`, correct/delete `/events/<id>`, and delete
`/readings/<id>`. Event/reading actions use the **set** revision for `If-Match`.
The UI uses the existing mutation headers for every write. Histories and
financial links are owner-scoped; serialized derived distances are not stored
as duplicate financial or odometer records.
