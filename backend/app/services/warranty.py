"""
GearCargo - Warranty ledger (F2).

Computes which service / repair / consumable entries are still under warranty
from the warranty data ALREADY captured on each entry, instead of guessing from
the vehicle's age. Coverage uses "whichever comes first": when both a time and a
mileage limit are set, the item is in force only while BOTH remain.

Fields per entry:
  * ServiceEntry  — warranty_expires (explicit Date) | warranty_months, warranty_km
  * RepairEntry   — warranty_months, warranty_km
  * ConsumableEntry — warranty_months (dated from install_date/odometer)
"""

from datetime import date as _date

from dateutil.relativedelta import relativedelta


def _base_date(entry, source_type):
    """Date the warranty starts counting from."""
    if source_type == 'consumable':
        return getattr(entry, 'install_date', None) or entry.date
    return entry.date


def _ref_odometer(entry, source_type):
    """Odometer at which the warranty started (for km-limit maths)."""
    if source_type == 'consumable':
        io = getattr(entry, 'install_odometer', None)
        return io if io is not None else entry.odometer
    return entry.odometer


def _label(entry, source_type):
    """Short, human-readable label. Prefers the user's title, else a humanised
    type token (e.g. 'oil_filter' -> 'Oil filter'). Type identifiers only — not
    a translatable UI string."""
    title = (getattr(entry, 'title', None) or '').strip()
    if title:
        return title
    token = (
        getattr(entry, 'consumable_type', None)
        or getattr(entry, 'service_type', None)
        or getattr(entry, 'repair_type', None)
        or source_type
    )
    return str(token).replace('_', ' ').strip().capitalize()


def compute_item(entry, source_type, current_mileage=None, today=None):
    """Return a ledger dict for one entry, or None if it carries no warranty.

    The dict includes ``in_force`` (bool) and ``days_left``/``km_left`` (may be
    None when that dimension isn't defined/known).
    """
    today = today or _date.today()

    warranty_km = getattr(entry, 'warranty_km', None)      # service/repair only
    months = getattr(entry, 'warranty_months', None)
    explicit = getattr(entry, 'warranty_expires', None)    # service only

    if not explicit and not months and not warranty_km:
        return None  # no warranty captured on this entry

    expires_on = explicit
    if expires_on is None and months:
        base = _base_date(entry, source_type)
        if base:
            expires_on = base + relativedelta(months=int(months))

    days_left = (expires_on - today).days if expires_on else None

    ref_odo = _ref_odometer(entry, source_type)
    km_left = None
    if warranty_km and ref_odo is not None and current_mileage is not None:
        km_left = int(warranty_km) - (int(current_mileage) - int(ref_odo))

    has_time = expires_on is not None
    has_km = km_left is not None
    time_ok = days_left is not None and days_left >= 0
    km_ok = km_left is not None and km_left > 0

    # "Whichever comes first": both limits must still hold when both are defined.
    if has_time and has_km:
        in_force = time_ok and km_ok
    elif has_time:
        in_force = time_ok
    elif has_km:
        in_force = km_ok
    else:
        in_force = False

    return {
        'id': entry.id,
        'vehicle_id': entry.vehicle_id,
        'source_type': source_type,
        'type': (getattr(entry, 'consumable_type', None)
                 or getattr(entry, 'service_type', None)
                 or getattr(entry, 'repair_type', None)),
        'label': _label(entry, source_type),
        'date': entry.date.isoformat() if entry.date else None,
        'expires_on': expires_on.isoformat() if expires_on else None,
        'days_left': days_left,
        'warranty_km': int(warranty_km) if warranty_km else None,
        'km_left': km_left,
        'in_force': in_force,
    }


def _warranty_entries(vehicle_id):
    """Fetch only entries that actually carry warranty data (bounded per vehicle)."""
    from app.models import ServiceEntry, RepairEntry, ConsumableEntry

    services = ServiceEntry.query.filter(
        ServiceEntry.vehicle_id == vehicle_id,
        db_or(ServiceEntry.warranty_expires.isnot(None),
              ServiceEntry.warranty_months.isnot(None),
              ServiceEntry.warranty_km.isnot(None)),
    ).all()
    repairs = RepairEntry.query.filter(
        RepairEntry.vehicle_id == vehicle_id,
        db_or(RepairEntry.warranty_months.isnot(None),
              RepairEntry.warranty_km.isnot(None)),
    ).all()
    consumables = ConsumableEntry.query.filter(
        ConsumableEntry.vehicle_id == vehicle_id,
        ConsumableEntry.warranty_months.isnot(None),
    ).all()
    return (
        [(e, 'service') for e in services]
        + [(e, 'repair') for e in repairs]
        + [(e, 'consumable') for e in consumables]
    )


def db_or(*clauses):
    from app import db
    return db.or_(*clauses)


def build_vehicle_warranties(vehicle, today=None):
    """In-force warranty items for one vehicle, soonest-to-expire first."""
    today = today or _date.today()
    items = []
    for entry, source_type in _warranty_entries(vehicle.id):
        item = compute_item(entry, source_type,
                            current_mileage=vehicle.current_mileage, today=today)
        if item and item['in_force']:
            items.append(item)
    # Soonest expiry first; km-only items (days_left None) sort last.
    items.sort(key=lambda x: (x['days_left'] is None, x['days_left'] if x['days_left'] is not None else 0))
    return items


def warranty_summary(vehicle, today=None):
    """Lightweight {count, nearest_days_left} for the health endpoint."""
    items = build_vehicle_warranties(vehicle, today=today)
    days = [i['days_left'] for i in items if i['days_left'] is not None]
    return {'count': len(items), 'nearest_days_left': min(days) if days else None}
