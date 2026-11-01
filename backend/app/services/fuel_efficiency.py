"""
GearCargo - Full-to-full fuel efficiency (F29).

Standard full-to-full accounting: only a FULL-tank fill with a usable odometer
yields an efficiency point — its consumption is its own litres PLUS every
partial fill's litres logged since the previous full tank, divided by the
odometer distance from that previous full tank. Partial fills carry no
efficiency of their own (fuel_efficiency / trip_distance = None), so a 20 L
top-up no longer produces bogus L/100km points that skew avg_consumption,
the health eco-score and the anomaly baseline.

Create/update/delete recalculate affected full-to-full windows. Imports walk
the complete history in batches. Existing derived values can be previewed and
rebuilt outside HTTP requests with the unit_rebuild maintenance CLI.
"""

# A memory/flush bound, never a limit on the history considered.
BATCH_SIZE = 256


def _position(entry):
    return entry.date, entry.id


def _before(position):
    from sqlalchemy import and_, or_
    from app.models import FuelEntry
    day, entry_id = position
    return or_(FuelEntry.date < day, and_(FuelEntry.date == day, FuelEntry.id < entry_id))


def _after(position):
    from sqlalchemy import and_, or_
    from app.models import FuelEntry
    day, entry_id = position
    return or_(FuelEntry.date > day, and_(FuelEntry.date == day, FuelEntry.id > entry_id))


def _batched_entries(query):
    """Keyset traversal with bounded dirty state; never commit a partial walk."""
    from app import db
    from app.models import FuelEntry
    cursor = None
    while True:
        page = query.filter(_after(cursor)) if cursor is not None else query
        entries = page.order_by(FuelEntry.date.asc(), FuelEntry.id.asc()).limit(BATCH_SIZE).all()
        if not entries:
            return
        yield from entries
        cursor = _position(entries[-1])
        # Flushed objects can leave SQLAlchemy's weak identity map as the next
        # page is loaded. Flush remains in the caller's transaction: interruption
        # rolls back source changes and every derived page together.
        db.session.flush()


def recalculate_efficiencies(vehicle_id, user_id, *, positions=None):
    """Recompute fuel_efficiency / trip_distance for one vehicle's history.

    With no positions, walk the entire history. For a single-record mutation,
    supply its old/new (date, id) positions: each affected window begins at the
    preceding full odometer anchor and ends at the next full odometer anchor.
    Moving an entry visits two windows, not every intervening year of history.
    Mutated and flushed rows remain in the current session — the CALLER commits.
    """
    from app import db
    from app.models import FuelEntry, Vehicle

    db.session.flush()  # Include newly assigned IDs, edits and pending deletes.
    history = FuelEntry.query.filter(FuelEntry.vehicle_id == vehicle_id, FuelEntry.user_id == user_id)
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=user_id).first()
    unit = vehicle.distance_unit if vehicle else None

    for position in sorted(set(positions)) if positions is not None else [None]:
        query, baseline_id = history, None
        if position is not None:
            anchors = history.filter(FuelEntry.full_tank.is_(True), FuelEntry.odometer.isnot(None))
            baseline = anchors.filter(_before(position)).order_by(FuelEntry.date.desc(), FuelEntry.id.desc()).first()
            following = anchors.filter(_after(position)).order_by(FuelEntry.date.asc(), FuelEntry.id.asc()).first()
            if baseline:
                baseline_id = baseline.id
                query = query.filter(~_before(_position(baseline)))
            if following:
                query = query.filter(~_after(_position(following)))
        # The pure walker retains its anchor and accumulated partial litres
        # across every page. A preceding anchor seeds the state but its own
        # efficiency belongs to an earlier, unaffected observation window.
        for entry, distance, efficiency in derive_efficiencies(_batched_entries(query), unit):
            if entry.id != baseline_id:
                entry.trip_distance = distance
                entry.fuel_efficiency = efficiency
    if vehicle:
        # Consumption contributes to the health score; imported/stored caches
        # must never survive a rebuild using a different unit calculation.
        vehicle.avg_fuel_efficiency = vehicle.cost_per_km = None
        vehicle.health_score = vehicle.health_computed_at = None


def derive_efficiencies(entries, unit):
    """Pure full-to-full walk; each yielded distance keeps the vehicle unit.

    Missing/invalid volume breaks an observation window, never invents zero fuel.
    Missing odometers on otherwise measured fills still accumulate consumption.
    """
    import math
    from app.utils.units import distance_to_km
    last_full_odo = None
    pending_liters = 0.0
    for entry in entries:
        try:
            liters = float(entry.liters)
            usable = math.isfinite(liters) and liters >= 0
        except (ValueError, TypeError, OverflowError):
            usable = False
        odo = entry.odometer
        if not usable or (odo is not None and (not isinstance(odo, int) or isinstance(odo, bool) or not 0 <= odo <= 2147483647)):
            last_full_odo = None
            pending_liters = 0.0
            yield entry, None, None
            continue
        if entry.full_tank and odo is not None:
            distance = odo - last_full_odo if last_full_odo is not None and odo > last_full_odo else None
            km = distance_to_km(distance, unit)
            efficiency = (liters + pending_liters) / float(km) * 100 if km else None
            yield entry, distance, efficiency
            last_full_odo = odo
            pending_liters = 0.0
        else:
            yield entry, None, None
            pending_liters += liters


def weighted_efficiency_query(*filters):
    """Distance-weighted canonical L/100km across known vehicle units, in SQL."""
    from app import db
    from app.models import FuelEntry, Vehicle
    from sqlalchemy import case, func
    from app.utils.units import KM_PER_MILE

    km = FuelEntry.trip_distance * case(
        (Vehicle.distance_unit.in_(('miles', 'mi')), float(KM_PER_MILE)),
        (Vehicle.distance_unit == 'km', 1.0), else_=None)
    numerator, denominator = db.session.query(
        func.sum(FuelEntry.fuel_efficiency * km), func.sum(km)
    ).join(Vehicle).filter(
        *filters, FuelEntry.fuel_efficiency.isnot(None),
        FuelEntry.fuel_efficiency >= 0, FuelEntry.trip_distance > 0,
    ).one()
    return float(numerator / denominator) if denominator else None


def weighted_efficiency(entries):
    """Single-vehicle subsets have a common distance unit; its factor cancels."""
    usable = [e for e in entries if e.fuel_efficiency is not None and e.trip_distance and e.trip_distance > 0]
    distance = sum(e.trip_distance for e in usable)
    return sum(e.fuel_efficiency * e.trip_distance for e in usable) / distance if distance else None
