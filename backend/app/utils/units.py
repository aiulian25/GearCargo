"""GC-015 quantity contract: vehicle-unit distances, litres, and L/100km.

Distance-bearing history keeps its vehicle's declared unit. Unknown units stay
unknown. Gallon standards are explicit at import/input boundaries.
"""
from decimal import Decimal, ROUND_HALF_UP

from app.utils.entryparse import InvalidFieldError, parse_amount, parse_optional_int

KM_PER_MILE = Decimal('1.609344')
LITERS_PER_GALLON = {
    'liters': Decimal('1'),
    'us_gallons': Decimal('3.785411784'),
    'imperial_gallons': Decimal('4.54609'),
}


def distance_unit(unit):
    if unit in ('miles', 'mi'):
        return 'miles'
    return 'km' if unit == 'km' else None


def distance_to_km(value, unit):
    normalized = distance_unit(unit)
    if value is None or normalized is None:
        return None
    return parse_amount(value) * (KM_PER_MILE if normalized == 'miles' else 1)


def convert_odometer(value, source, target):
    if distance_unit(source) is None or distance_unit(target) is None:
        raise InvalidFieldError('validation.invalidValue', 'Declare the source and target distance units', 'distance_unit')
    value = parse_optional_int(value)
    if value is None:
        return None
    converted = distance_to_km(value, source)
    if distance_unit(target) == 'miles':
        converted /= KM_PER_MILE
    return parse_optional_int(converted.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def volume_to_liters(value, source_unit):
    if source_unit not in LITERS_PER_GALLON:
        raise InvalidFieldError('validation.invalidValue', 'Choose litres, US gallons or imperial gallons', 'source_volume_unit')
    return parse_amount(value) * LITERS_PER_GALLON[source_unit]


def distance_unit_locked(vehicle):
    """Prevent a unit edit from relabelling any existing history or thresholds."""
    from app import db
    from app.models import Entry, Reminder, Todo, InsurancePolicy, PredictionAlert, TireSet
    if vehicle.current_mileage or vehicle.avg_trip_distance or vehicle.maintenance_intervals:
        return True
    for model in (Entry, Reminder, Todo, InsurancePolicy, PredictionAlert, TireSet):
        if db.session.query(model.id).filter_by(vehicle_id=vehicle.id).first() is not None:
            return True
    return False
