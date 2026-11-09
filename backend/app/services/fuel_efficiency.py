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

measure_fills also names why a fill has no figure (GC-105). Reads derive that
status with measurement_statuses; nothing is stored.
"""

import math
from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter

from app.utils.entryparse import INT32_MAX

# A memory/flush bound, never a limit on the history considered.
BATCH_SIZE = 256

MEASURED = 'measured'
PARTIAL = 'partial'
FIRST_FULL_FILL = 'first_full_fill'
ODOMETER_REGRESSION = 'odometer_regression'
ODOMETER_MISSING = 'odometer_missing'
ODOMETER_INVALID = 'odometer_invalid'
VOLUME_INVALID = 'volume_invalid'
DISTANCE_UNIT_UNKNOWN = 'distance_unit_unknown'

ODOMETER_REGRESSION_MESSAGE = (
    "The odometer is not above the previous full-tank reading ({previous}), so this fill's "
    'consumption cannot be measured. The next full tank will be measured from this reading; '
    'edit it if it was a typo.')


@dataclass(frozen=True, slots=True)
class FuelMeasurement:
    """One fill's outcome. previous_odometer is the full-tank anchor in force before the fill."""
    distance: int | None
    efficiency: float | None
    status: str
    previous_odometer: int | None


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

    Returns {entry_id: FuelMeasurement} for each entry named in positions that
    still exists, never taken from a window that entry only seeds. A full walk
    returns {}, so imports keep the BATCH_SIZE memory bound.
    """
    from app import db
    from app.models import FuelEntry, Vehicle

    db.session.flush()  # Include newly assigned IDs, edits and pending deletes.
    history = FuelEntry.query.filter(FuelEntry.vehicle_id == vehicle_id, FuelEntry.user_id == user_id)
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=user_id).first()
    unit = vehicle.distance_unit if vehicle else None
    requested_ids = {entry_id for _, entry_id in positions or ()}
    measurements = {}

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
        for entry, measurement in measure_fills(_batched_entries(query), unit):
            if entry.id == baseline_id:
                continue
            entry.trip_distance = measurement.distance
            entry.fuel_efficiency = measurement.efficiency
            if entry.id in requested_ids:
                measurements[entry.id] = measurement
    if vehicle:
        # Consumption contributes to the health score; imported/stored caches
        # must never survive a rebuild using a different unit calculation.
        vehicle.avg_fuel_efficiency = vehicle.cost_per_km = None
        vehicle.health_score = vehicle.health_computed_at = None
    return measurements


def _measurable_liters(value):
    """A finite, non-negative volume, or None. Zero litres is a real measurement."""
    try:
        liters = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(liters) or liters < 0:
        return None
    return liters


def _is_valid_odometer(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= INT32_MAX


def _full_fill_measurement(odometer, previous_odometer, consumed, unit):
    from app.utils.units import distance_to_km
    if previous_odometer is None:
        return FuelMeasurement(None, None, FIRST_FULL_FILL, None)
    if odometer <= previous_odometer:
        return FuelMeasurement(None, None, ODOMETER_REGRESSION, previous_odometer)
    distance = odometer - previous_odometer
    km = distance_to_km(distance, unit)
    if km is None:
        return FuelMeasurement(distance, None, DISTANCE_UNIT_UNKNOWN, previous_odometer)
    return FuelMeasurement(distance, consumed / float(km) * 100, MEASURED, previous_odometer)


def measure_fills(entries, unit):
    """Pure full-to-full walk yielding (entry, FuelMeasurement); distances keep the vehicle unit.

    Missing/invalid volume breaks an observation window, never invents zero fuel.
    Missing odometers on otherwise measured fills still accumulate consumption.
    A full fill not above the previous full-tank reading re-anchors and drops
    pending litres.
    """
    anchor_odometer = None
    pending_liters = 0.0
    for entry in entries:
        previous_odometer = anchor_odometer
        liters = _measurable_liters(entry.liters)
        odometer = entry.odometer
        if liters is None:
            anchor_odometer, pending_liters = None, 0.0
            yield entry, FuelMeasurement(None, None, VOLUME_INVALID, previous_odometer)
            continue
        if odometer is not None and not _is_valid_odometer(odometer):
            anchor_odometer, pending_liters = None, 0.0
            yield entry, FuelMeasurement(None, None, ODOMETER_INVALID, previous_odometer)
            continue
        if not entry.full_tank:
            pending_liters += liters
            yield entry, FuelMeasurement(None, None, PARTIAL, previous_odometer)
            continue
        if odometer is None:
            pending_liters += liters
            yield entry, FuelMeasurement(None, None, ODOMETER_MISSING, previous_odometer)
            continue
        consumed = liters + pending_liters
        anchor_odometer, pending_liters = odometer, 0.0
        yield entry, _full_fill_measurement(odometer, previous_odometer, consumed, unit)


def derive_efficiencies(entries, unit):
    """The (entry, distance, efficiency) view kept for unit_rebuild and existing callers."""
    for entry, measurement in measure_fills(entries, unit):
        yield entry, measurement.distance, measurement.efficiency


def measurement_warnings(measurement):
    """Non-blocking save feedback: a lower reading can be a legitimate correction."""
    if measurement is None or measurement.status != ODOMETER_REGRESSION:
        return []
    previous_odometer = measurement.previous_odometer
    return [{'code': ODOMETER_REGRESSION, 'previous': previous_odometer,
             'message': ODOMETER_REGRESSION_MESSAGE.format(previous=previous_odometer)}]


def measurement_statuses(user_id, vehicle_ids):
    """{entry_id: status} from one ordered read of the listed vehicles' complete histories.

    A status can depend on an anchor far back, so a page is never measured on its own.
    """
    from app import db
    from app.models import FuelEntry, Vehicle

    if not vehicle_ids:
        return {}
    # ponytail: re-walks complete histories on every read; persist or cache statuses if list latency matters.
    rows = db.session.query(
        FuelEntry.id, FuelEntry.vehicle_id, FuelEntry.odometer, FuelEntry.liters,
        FuelEntry.full_tank, Vehicle.distance_unit,
    ).join(Vehicle, Vehicle.id == FuelEntry.vehicle_id).filter(
        FuelEntry.user_id == user_id, Vehicle.user_id == user_id, FuelEntry.vehicle_id.in_(vehicle_ids),
    ).order_by(FuelEntry.vehicle_id, FuelEntry.date, FuelEntry.id)
    statuses = {}
    for (_, unit), history in groupby(rows, key=attrgetter('vehicle_id', 'distance_unit')):
        for row, measurement in measure_fills(history, unit):
            statuses[row.id] = measurement.status
    return statuses


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
