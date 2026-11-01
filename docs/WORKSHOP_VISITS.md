# Workshop appointments and visits

Open **Vehicle → Alerts → Plan workshop visit**, or select a vehicle in
**Calendar** and choose **Plan workshop visit**. Create a request with a title,
optional workshop/contact details, a proposed drop-off and pick-up time, and an
IANA time zone such as `Europe/London`. Status is recorded manually by the owner.
GearCargo does not contact workshops, send booking requests, or verify acceptance.

Select due reminders, todos, service obligations or prediction alerts and add
custom preparation checklist items. Due work uses the existing due feed's horizon
and dismissals. Other obligation types remain in their existing screens. Custom
checklist items can be checked during preparation; linked work is resolved only
when explicitly selected at completion.

After arranging the visit externally, choose **Mark confirmed** and acknowledge
that you have agreed the time with the workshop. Changing the time, time zone or
workshop returns the visit to requested and requires confirmation again. Choose
push and/or email to yourself for preparation reminders. Existing account and
channel preferences still apply. No channels are selected automatically. The
reminder becomes eligible at the chosen number of minutes before the appointment;
delivery follows the existing scheduler cadence, with per-occurrence/channel
claims and retry behavior. Drop-off, cancellation and completion stop preparation
notifications. Notification links open the existing reminder detail with a link
to workshop visits. Already delivered notifications cannot be recalled.

Use **Record drop-off** when handing over the vehicle. It records the current
instant once. At collection, choose **Complete visit**. Record service/repair
costs and receipts using the existing expense forms, then return and select the
expenses to link. An expense can belong to one visit; the link creates no new
expense or receipt and does not change its currency. A no-expense visit requires
an explicit checkbox. Existing expenses appear in the vehicle timeline as usual.
Completion records pick-up time and resolves only selected work, atomically.
Recurring todos/reminders retain their next occurrence. A recurring mileage
reminder without a repeat interval must be configured or completed separately.
Changed/deleted linked work blocks resolution: remove the old linked item and
select the current work again after review. Unselected obligations remain open.

Completed/cancelled visits are history, not editable bookings. Archived vehicles
are read-only and their automated activity is paused. Cancellation leaves work
and expenses unchanged. Permanent vehicle/account deletion includes all workshop
records; deleting an expense removes its visit link, not the visit history.

## Time zones, calendar and offline use

Schedule fields are local wall times plus a named time zone. Nonexistent times
at spring clock changes are rejected. For a repeated autumn hour, explicitly
choose the earlier or later occurrence under daylight-saving options. Stored
instants use UTC; the visit and calendar show the appointment's named-zone time.
Actual drop-off and pick-up are separate timestamps from the proposed schedule.
The calendar day follows that time zone even when its UTC date differs.

An enabled owner calendar source receives one stable appointment UID through the
existing transactional outbox. Reschedules update it; cancellation deletes it;
completion retains the event without a preparation alarm. The internal preparation
reminder does not create a second calendar event. This synchronizes the owner's
configured calendar only, not a workshop booking system.

New requests can be saved in the account-bound offline queue after acknowledgment
from the service worker and replay once connectivity returns. Offline requests
remain unconfirmed. Existing visit edits, confirmation, cancellation, drop-off
and completion require a connection and the displayed record revision. Conflicts
remain visible for review instead of silently replacing newer changes.

## Data and recovery

`feature_appointments` follows `feature_tires_lifecycle` and adds `appointments`,
`appointment_tasks`, and `appointment_expenses`. Apply through normal container
startup or `flask db upgrade`. Downgrade removes these tables; retain a compatible
backup first. This implementation task does not migrate production.

Portable backup format **4.6** includes all three collections and remaps vehicle,
preparation reminder, task, and expense references. It validates time zones,
chronology, status and link ownership before writing. Formats 4.0–4.5 remain
readable; omitted newer collections are empty. Older applications cannot read
4.6 exports. System archives still require a compatible database schema.

The owner API is `/api/appointments`: list/create, `/<id>` get/update,
`/work?vehicle_id=…` for linkable due work, and `/<id>/confirm`, `/cancel`,
`/dropoff`, `/complete` for explicit transitions. Writes use existing mutation
receipts; edits/transitions use the appointment revision. Contacts remain
owner-scoped and are omitted from external calendar payloads.
