"""Owner-scoped lifecycle rules shared by API, due feed and portable backups."""
from decimal import Decimal, InvalidOperation
from app import db
from app.models import Vehicle, Entry
from app.models.tire import TireSet, FitmentEvent
from app.utils.entryparse import InvalidFieldError, parse_optional_date
from app.utils.timeutils import utc_today, isoformat_utc
from app.utils.units import distance_to_km

POSITIONS = ('FL', 'FR', 'RL', 'RR')
TREAD_UNITS = ('mm', '32nds')


def invalid(field):
    raise InvalidFieldError('tires.invalid', 'Review tire details, dates, positions and odometers.', field)


def number(value, field, maximum=100000000, optional=True):
    if optional and value in (None, ''):
        return None
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > maximum:
            raise ValueError()
        return result
    except (ValueError, InvalidOperation):
        invalid(field)


def day(value):
    result = parse_optional_date(value)
    if result is None or result > utc_today():
        invalid('date')
    return result


def text(value, field, limit, required=False):
    if value in (None, '') and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        invalid(field)
    return value.strip()


def depth_mm(value, unit):
    if unit not in TREAD_UNITS:
        invalid('unit')
    return Decimal(str(value)) * (Decimal('0.79375') if unit == '32nds' else 1)


def validate_history(sets, events):
    """Validate a vehicle's entire timeline, including corrections and imports."""
    identifiers = {s['id']: {t['identifier'] for t in s['tires']} for s in sets}
    for s in sets:
        if len(s['tires']) != 4 or len(identifiers[s['id']]) != 4:
            invalid('tires')
    installed = None
    last_positions = None
    last_odometer = None
    for event in sorted(events, key=lambda e: (e['date'], e['id'])):
        if event['tire_set_id'] not in identifiers or event['kind'] not in ('install', 'remove', 'rotate'):
            invalid('kind')
        positions = event['positions']
        if not isinstance(positions, dict) or set(positions) != set(POSITIONS) or \
                any(not isinstance(v, str) for v in positions.values()) or \
                set(positions.values()) != identifiers[event['tire_set_id']]:
            invalid('positions')
        odometer = number(event['odometer'], 'odometer')
        if odometer is not None and last_odometer is not None and odometer < last_odometer:
            invalid('odometer')
        if odometer is not None:
            last_odometer = odometer
        if event['kind'] == 'install':
            if installed is not None:
                invalid('kind')
            installed = event['tire_set_id']
        elif installed != event['tire_set_id']:
            invalid('kind')
        elif event['kind'] == 'remove':
            if positions != last_positions:
                invalid('positions')
            installed = None
        elif positions == last_positions:
            invalid('positions')
        last_positions = positions


def event_dict(event):
    return {k: getattr(event, k) for k in ('id', 'tire_set_id', 'kind', 'date', 'odometer', 'positions')}


def validate_vehicle(vehicle_id):
    sets = TireSet.query.filter_by(vehicle_id=vehicle_id).all()
    validate_history([{'id': s.id, 'tires': [{'identifier': t.identifier} for t in s.tires]} for s in sets],
                     [event_dict(e) for e in FitmentEvent.query.filter_by(vehicle_id=vehicle_id)])


def serialize_set(record):
    vehicle = db.session.get(Vehicle, record.vehicle_id)
    events = sorted(record.events, key=lambda e: (e.date, e.id))
    distance = Decimal(0); unknown = 0; start = None; installed = False; rotation = None; latest_odometer = None
    rotation_distance = Decimal(0); rotation_unknown = False
    positions = dict(zip(POSITIONS, [t.identifier for t in record.tires]))
    for event in events:
        if event.kind == 'install':
            latest_odometer = event.odometer
        elif event.odometer is not None:
            latest_odometer = event.odometer
        if event.kind == 'install':
            installed, start, rotation = True, event.odometer, event.odometer
        elif event.kind == 'rotate':
            rotation = event.odometer
            rotation_distance, rotation_unknown = Decimal(0), False
        else:
            if rotation is None or event.odometer is None or event.odometer < rotation:
                rotation_unknown = True
            else:
                rotation_distance += event.odometer - rotation
            if start is None or event.odometer is None or event.odometer < start:
                unknown += 1
            else:
                distance += event.odometer - start
            installed, start = False, None
        positions = event.positions
    if installed:
        current = vehicle.current_mileage
        if start is None or current is None or current < start or (latest_odometer is not None and current < latest_odometer):
            unknown += 1
        else:
            distance += Decimal(current) - start
    remaining = None
    if installed and not rotation_unknown and rotation is not None and record.rotation_interval and vehicle.current_mileage is not None and vehicle.current_mileage >= rotation:
        remaining = record.rotation_interval - rotation_distance - (Decimal(vehicle.current_mileage) - rotation)
    latest = {}
    readings = sorted(record.readings, key=lambda r: (r.date, r.id))
    for reading in readings:
        latest[reading.tire_id] = reading
    alerts = []
    if remaining is not None and remaining <= 0:
        alerts.append('rotation')
    if record.tread_threshold is not None and any(depth_mm(r.depth, r.unit) <= depth_mm(record.tread_threshold, record.tread_unit) for r in latest.values()):
        alerts.append('tread')
    def numeric(v): return float(v) if v is not None else None
    purchase = db.session.get(Entry, record.purchase_entry_id) if record.purchase_entry_id else None
    return {
        'id': record.id, 'revision': record.revision, 'vehicle_id': record.vehicle_id,
        'name': record.name, 'season': record.season, 'storage_location': record.storage_location,
        'purchase_entry_id': record.purchase_entry_id,
        'purchase': {'id': purchase.id, 'type': purchase.type, 'title': purchase.title, 'amount': numeric(purchase.amount), 'currency': purchase.currency} if purchase else None,
        'rotation_interval': numeric(record.rotation_interval), 'tread_unit': record.tread_unit,
        'tread_threshold': numeric(record.tread_threshold), 'installed': installed,
        'distance_unit': vehicle.distance_unit, 'known_distance': numeric(distance),
        'known_distance_km': numeric(distance_to_km(distance, vehicle.distance_unit)),
        'distance': None if unknown else numeric(distance), 'unknown_intervals': unknown,
        'rotation_remaining': numeric(remaining), 'alerts': alerts, 'positions': positions,
        'tires': [{'id': t.id, 'identifier': t.identifier} for t in record.tires],
        'events': [{**event_dict(e), 'date': e.date.isoformat(), 'odometer': numeric(e.odometer)} for e in events],
        'readings': [{'id': r.id, 'tire_id': r.tire_id, 'date': r.date.isoformat(), 'depth': numeric(r.depth), 'unit': r.unit} for r in readings],
        'created_at': isoformat_utc(record.created_at),
    }


def validate_backup_tires(records):
    """Reject contradictory portable links/history before restoration starts."""
    from app.services.backup_schema import BackupSchemaError, ENTRY_COLLECTIONS
    try:
        sets = {row['id']: row for row in records['tire_sets']}
        tires = {row['id']: row for row in records['tires']}
        vehicles = {row['id']: row for row in records['vehicles']}
        entries = {row['id']: row for kind in ENTRY_COLLECTIONS for row in records[kind]}
        for row in sets.values():
            text(row['name'], 'name', 100, True)
            text(row['storage_location'], 'storage_location', 200)
            if row['season'] not in ('summer', 'winter', 'all_season') or row['tread_unit'] not in TREAD_UNITS:
                invalid('tire_sets')
            interval = number(row['rotation_interval'], 'rotation_interval')
            if interval == 0:
                invalid('rotation_interval')
            number(row['tread_threshold'], 'tread_threshold', 100)
            if vehicles[row['vehicle_id']]['distance_unit'] not in ('km', 'miles'):
                invalid('vehicle_id')
            if row['purchase_entry_id'] is not None and entries[row['purchase_entry_id']]['vehicle_id'] != row['vehicle_id']:
                invalid('purchase_entry_id')
        for kind in ('tires', 'tire_fitments', 'tread_readings'):
            for row in records[kind]:
                if sets[row['tire_set_id']]['vehicle_id'] != row['vehicle_id']:
                    invalid('vehicle_id')
                if kind == 'tires':
                    text(row['identifier'], 'identifier', 60, True)
                else:
                    day(row['date'].isoformat())
                if kind == 'tread_readings':
                    if tires[row['tire_id']]['tire_set_id'] != row['tire_set_id']:
                        invalid('tire_id')
                    depth_mm(number(row['depth'], 'depth', 100, optional=False), row['unit'])
        for vehicle_id in {row['vehicle_id'] for row in sets.values()}:
            validate_history([{**row, 'tires': [t for t in tires.values() if t['tire_set_id'] == row['id']]} for row in sets.values() if row['vehicle_id'] == vehicle_id],
                             [e for e in records['tire_fitments'] if e['vehicle_id'] == vehicle_id])
    except (InvalidFieldError, KeyError, TypeError, AttributeError):
        raise BackupSchemaError('Tire identities, links or lifecycle history are inconsistent.', 'tire_sets') from None
