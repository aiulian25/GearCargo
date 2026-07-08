"""GearCargo - Unified "Due & Expiring" aggregator (F4).

Merges the per-type due/expiry signals that were previously scattered across six
endpoints (reminders, service next-due, tax, insurance, documents, parking
permits) plus F3's consumable-replacement wear into ONE ranked list, so the
dashboard can answer "what needs attention?" fleet-wide in a single request.

Every item is normalised to::

    {kind, ref_id, title, vehicle_id, vehicle_name, due_date, days_left,
     severity, link}

``severity`` is derived once, here, from ``days_left`` (or wear status for
consumables) so the frontend never re-implements the urgency rule:

    days_left < 0            -> 'critical'  (overdue / expired)
    0 <= days_left <= WARN   -> 'warning'
    otherwise                -> 'info'

Ownership is enforced by scoping every query to ``user_id`` and (for
vehicle-bound entries) to the user's NON-archived vehicles. No cross-user data
can leak; the aggregator is read-only.

NOTE: this deliberately queries the models' REAL columns. Several legacy
per-type endpoints filter columns that do not exist on the current models
(``TaxEntry.valid_until``, ``ParkingEntry.is_permit``/``permit_valid_until``,
``ServiceEntry.next_service_date``) and would error if hit; F4 supersedes them
without depending on them.
"""

from datetime import date, timedelta

from sqlalchemy import func

from app import db
from app.models import (
    Vehicle, Reminder, ServiceEntry, TaxEntry, InsurancePolicy,
    Attachment, ParkingEntry, ConsumableEntry, DueDismissal,
)

# Items due within this many days count as "warning" (amber); further out is
# informational. Overdue (days_left < 0) is always "critical".
WARN_DAYS = 7

# Hard cap on the returned list so a large fleet with lots of history can't
# produce an unbounded payload (PWA/offline friendliness). Sorted by urgency
# first, so the cap only ever drops the least-urgent, furthest-out items.
MAX_ITEMS = 60

_SEVERITY_RANK = {'critical': 0, 'warning': 1, 'info': 2}


def _severity(days_left):
    if days_left is None:
        return 'info'
    if days_left < 0:
        return 'critical'
    if days_left <= WARN_DAYS:
        return 'warning'
    return 'info'


def _days_left(due, today):
    return (due - today).days if due else None


def build_due_items(user_id, days=30, today=None):
    """Assemble the ranked "due & expiring" list for one user.

    ``days`` sets the FORWARD horizon (default 30). Overdue items are always
    included regardless of how far past — an unresolved overdue reminder or an
    expired policy still needs attention — matching the existing ``/overdue``
    semantics. The final list is capped at ``MAX_ITEMS`` after urgency sorting.
    """
    today = today or date.today()
    cutoff = today + timedelta(days=max(0, days))

    # --- vehicle lookup (one query) -------------------------------------------
    # name map covers ALL owned vehicles (so labels resolve even for archived);
    # active_ids restricts vehicle-bound entries to non-archived vehicles.
    vehicles = Vehicle.query.filter_by(user_id=user_id).all()
    vname = {
        v.id: (v.name or f"{v.make or ''} {v.model or ''}".strip() or 'Vehicle')
        for v in vehicles
    }
    active = {v.id: v for v in vehicles if not v.archived}
    active_ids = list(active.keys())

    # User dismissals: (kind, ref_id, occurrence due_date). An item whose
    # CURRENT effective due date matches a stored dismissal is hidden; once a
    # recurring obligation advances to a new date it resurfaces. Reminders are
    # not stored here (they use the native Reminder.dismissed flag, already
    # filtered below).
    dismissed = {
        (d.kind, d.ref_id, d.due_date)
        for d in DueDismissal.query.filter_by(user_id=user_id).all()
    }

    items = []

    def add(kind, ref_id, title, vehicle_id, due, link, days_left=None, severity=None):
        if (kind, ref_id, due) in dismissed:
            return
        dl = days_left if days_left is not None else _days_left(due, today)
        items.append({
            'kind': kind,
            'ref_id': ref_id,
            'title': title,
            'vehicle_id': vehicle_id,
            'vehicle_name': vname.get(vehicle_id),
            'due_date': due.isoformat() if due else None,
            'days_left': dl,
            'severity': severity or _severity(dl),
            'link': link,
        })

    # --- 1. Reminders (overdue + upcoming, user-scoped) -----------------------
    reminders = Reminder.query.filter(
        Reminder.user_id == user_id,
        Reminder.completed == False,   # noqa: E712
        Reminder.dismissed == False,   # noqa: E712
        Reminder.due_date.isnot(None),
        Reminder.due_date <= cutoff,
    ).all()
    for r in reminders:
        add('reminder', r.id, r.title, r.vehicle_id, r.due_date, '/reminders')

    if not active_ids:
        # No non-archived vehicles → only user-scoped reminders can apply.
        return _finalize(items)

    # --- 2. Service next-due --------------------------------------------------
    services = ServiceEntry.query.filter(
        ServiceEntry.vehicle_id.in_(active_ids),
        ServiceEntry.next_due_date.isnot(None),
        ServiceEntry.next_due_date <= cutoff,
    ).all()
    # A next-due pointer is SUPERSEDED once a newer service of the same type
    # was logged (the job was done; the newest entry carries the live pointer).
    # Without this, every historical entry's stale pointer nags forever.
    latest_svc = {
        (vid, stype): mx
        for vid, stype, mx in db.session.query(
            ServiceEntry.vehicle_id, ServiceEntry.service_type,
            func.max(ServiceEntry.date),
        ).filter(ServiceEntry.vehicle_id.in_(active_ids))
        .group_by(ServiceEntry.vehicle_id, ServiceEntry.service_type).all()
    } if services else {}
    for s in services:
        mx = latest_svc.get((s.vehicle_id, s.service_type))
        if mx and s.date and mx > s.date:
            continue  # a newer same-type service exists → pointer already handled
        title = (s.title or s.service_type or 'Service').replace('_', ' ')
        add('service', s.id, title, s.vehicle_id, s.next_due_date,
            f'/vehicles/{s.vehicle_id}/timeline?type=service&focus={s.id}')

    # --- 3. Tax due (next_due_date, else due_date) ----------------------------
    # The due_date branch (one-time taxes) excludes settled rows: a paid or
    # cancelled tax is done — its past due date is not actionable. The
    # next_due_date branch (recurring templates) is about the NEXT, unpaid
    # occurrence, so the row's own paid status is irrelevant there.
    taxes = TaxEntry.query.filter(
        TaxEntry.vehicle_id.in_(active_ids),
        db.or_(
            TaxEntry.next_due_date <= cutoff,
            db.and_(
                TaxEntry.next_due_date.is_(None),
                TaxEntry.due_date <= cutoff,
                db.or_(TaxEntry.status.is_(None),
                       TaxEntry.status.notin_(('paid', 'cancelled'))),
            ),
        ),
    ).all()
    for tx in taxes:
        eff = tx.next_due_date or tx.due_date
        if not eff:
            continue
        title = (tx.title or tx.tax_type or 'Tax').replace('_', ' ')
        add('tax', tx.id, title, tx.vehicle_id, eff,
            f'/vehicles/{tx.vehicle_id}/timeline?type=tax&focus={tx.id}')

    # --- 4. Insurance expiry --------------------------------------------------
    policies = InsurancePolicy.query.filter(
        InsurancePolicy.user_id == user_id,
        InsurancePolicy.status == 'active',
        InsurancePolicy.end_date.isnot(None),
        InsurancePolicy.end_date <= cutoff,
    ).all()
    for p in policies:
        add('insurance', p.id, p.provider or 'Insurance', p.vehicle_id, p.end_date,
            f'/vehicles/{p.vehicle_id}/expenses')

    # --- 5. Document expiry (attachments) -------------------------------------
    docs = Attachment.query.filter(
        Attachment.user_id == user_id,
        Attachment.expires_at.isnot(None),
        Attachment.expires_at <= cutoff,
    ).all()
    for d in docs:
        title = d.original_filename or d.filename or d.category or 'Document'
        link = f'/vehicles/{d.vehicle_id}/search' if d.vehicle_id else '/vehicles'
        add('document', d.id, title, d.vehicle_id, d.expires_at, link)

    # --- 6. Parking permit expiry ---------------------------------------------
    permits = ParkingEntry.query.filter(
        ParkingEntry.vehicle_id.in_(active_ids),
        ParkingEntry.parking_type == 'permit',
        ParkingEntry.permit_expires.isnot(None),
        ParkingEntry.permit_expires <= cutoff,
    ).all()
    # A permit occurrence is SUPERSEDED once a renewal with a later expiry
    # exists for the same series (same vehicle + title/location) — an already
    # renewed permit's past expiry is not actionable.
    latest_permit = {
        (vid, ttl, loc): mx
        for vid, ttl, loc, mx in db.session.query(
            ParkingEntry.vehicle_id,
            func.lower(func.coalesce(ParkingEntry.title, '')),
            func.lower(func.coalesce(ParkingEntry.location, '')),
            func.max(ParkingEntry.permit_expires),
        ).filter(
            ParkingEntry.vehicle_id.in_(active_ids),
            ParkingEntry.parking_type == 'permit',
            ParkingEntry.permit_expires.isnot(None),
        ).group_by(
            ParkingEntry.vehicle_id,
            func.lower(func.coalesce(ParkingEntry.title, '')),
            func.lower(func.coalesce(ParkingEntry.location, '')),
        ).all()
    } if permits else {}
    for pk in permits:
        series = (pk.vehicle_id, (pk.title or '').lower(), (pk.location or '').lower())
        mx = latest_permit.get(series)
        if mx and mx > pk.permit_expires:
            continue  # a later renewal exists → this occurrence is history
        title = pk.title or pk.location or 'Parking permit'
        add('parking', pk.id, title, pk.vehicle_id, pk.permit_expires,
            f'/vehicles/{pk.vehicle_id}/timeline?type=parking&focus={pk.id}')

    # --- 6b. Parking fines outstanding (F14, no due_date) ---------------------
    fines = ParkingEntry.query.filter(
        ParkingEntry.vehicle_id.in_(active_ids),
        ParkingEntry.parking_type == 'fine',
        db.or_(
            ParkingEntry.fine_status.in_(('pending', 'contested')),
            ParkingEntry.fine_status.is_(None),
        ),
    ).all()
    for fn in fines:
        title = fn.fine_reason or fn.title or fn.location or 'Parking fine'
        add('fine', fn.id, title, fn.vehicle_id, None,
            f'/vehicles/{fn.vehicle_id}/timeline?type=parking&focus={fn.id}',
            days_left=None, severity='warning')

    # --- 7. Consumable replacement (F3 wear, no due_date) ---------------------
    consumables = ConsumableEntry.query.filter(
        ConsumableEntry.vehicle_id.in_(active_ids),
    ).all()
    for c in consumables:
        v = active.get(c.vehicle_id)
        wear = c.wear_estimate(current_mileage=v.current_mileage if v else None)
        status = wear.get('status')
        if status not in ('monitor', 'replace'):
            continue
        severity = 'critical' if status == 'replace' else 'warning'
        title = (c.title or c.consumable_type or 'Consumable').replace('_', ' ')
        add('consumable', c.id, title, c.vehicle_id, None,
            f'/vehicles/{c.vehicle_id}/consumables',
            days_left=None, severity=severity)

    return _finalize(items)


def _finalize(items):
    """Sort by urgency, collapse duplicates, and cap length.

    Duplicate collapse (F39): recurring reminders and generated recurring
    tax/parking rows can yield many rows with the same kind + vehicle + title
    (e.g. seven overdue "MOT" reminders). The feed answers "what needs
    attention?", so one row per (kind, vehicle, title) is enough — we keep the
    MOST URGENT occurrence (the list is already urgency-sorted, so the first
    seen wins) and record how many records it stands for in ``count`` so the
    UI can show "×N" and nothing is hidden silently. Different vehicles or
    kinds are never merged.
    """
    items.sort(key=lambda it: (
        _SEVERITY_RANK.get(it['severity'], 3),
        it['days_left'] if it['days_left'] is not None else 10 ** 9,
        it['kind'],
    ))

    deduped = []
    seen = {}  # (kind, vehicle_id, casefolded title) -> surviving item
    for it in items:
        key = (it['kind'], it['vehicle_id'], (it['title'] or '').strip().casefold())
        kept = seen.get(key)
        if kept is None:
            it['count'] = 1
            seen[key] = it
            deduped.append(it)
        else:
            kept['count'] += 1

    return deduped[:MAX_ITEMS]
