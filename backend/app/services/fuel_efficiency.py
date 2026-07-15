"""
GearCargo - Full-to-full fuel efficiency (F29).

Standard full-to-full accounting: only a FULL-tank fill with a usable odometer
yields an efficiency point — its consumption is its own litres PLUS every
partial fill's litres logged since the previous full tank, divided by the
odometer distance from that previous full tank. Partial fills carry no
efficiency of their own (fuel_efficiency / trip_distance = None), so a 20 L
top-up no longer produces bogus L/100km points that skew avg_consumption,
the health eco-score and the anomaly baseline.

There is no one-time backfill: the first create / update / delete touching a
vehicle's fuel history recalculates that vehicle lazily.
"""

# Hard cap on the walk — far above any real per-vehicle fill history.
MAX_ENTRIES = 2000


def recalculate_efficiencies(vehicle_id, user_id):
    """Recompute fuel_efficiency / trip_distance for one vehicle's history.

    Walks the vehicle's fuel entries ordered by (date, id) in a single pass.
    Mutates rows in the current session — the CALLER commits. Relies on
    autoflush so an entry just added/edited in this session is included.
    """
    from app.models import FuelEntry

    entries = (
        FuelEntry.query
        .filter(FuelEntry.vehicle_id == vehicle_id, FuelEntry.user_id == user_id)
        .order_by(FuelEntry.date.asc(), FuelEntry.id.asc())
        .limit(MAX_ENTRIES)
        .all()
    )

    last_full_odo = None    # odometer of the previous full-tank fill
    pending_liters = 0.0    # partial-fill litres since that full fill

    for e in entries:
        liters = float(e.liters or 0)
        if e.full_tank and e.odometer:
            if last_full_odo is not None and e.odometer > last_full_odo:
                distance = e.odometer - last_full_odo
                e.trip_distance = int(distance)
                e.fuel_efficiency = (liters + pending_liters) / distance * 100
            else:
                # First full fill, or a non-increasing odometer — no baseline.
                e.trip_distance = None
                e.fuel_efficiency = None
            # This fill starts the next full-to-full window either way.
            last_full_odo = e.odometer
            pending_liters = 0.0
        else:
            # Partial fill — or a full fill without an odometer reading, which
            # can't anchor a window: no efficiency point of its own, litres
            # belong to the next full-to-full window.
            e.trip_distance = None
            e.fuel_efficiency = None
            pending_liters += liters
