"""Tire lifecycle APIs. All actions share the set revision and operation receipt."""
from flask import Blueprint, jsonify, request
from app import db
from app.models import Vehicle, Entry, DueDismissal
from app.models.tire import TireSet, Tire, FitmentEvent, TreadReading
from app.routes.auth import token_required
from app.services.mutations import mutation_endpoint, commit_mutation
from app.services import tire_lifecycle as lifecycle
from app.utils.timeutils import utc_naive_now


tires_bp = Blueprint('tires', __name__)


def owned(user, set_id):
    return TireSet.query.filter_by(id=set_id, user_id=user.id).first_or_404()


def vehicle_for_write(user, vehicle_id):
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=user.id).with_for_update().first_or_404()
    if vehicle.archived or vehicle.distance_unit not in ('km', 'miles'):
        lifecycle.invalid('vehicle_id')
    return vehicle


def settings(record, data, user):
    if 'name' in data:
        record.name = lifecycle.text(data['name'], 'name', 100, True)
    if 'season' in data:
        if data['season'] not in ('summer', 'winter', 'all_season'):
            lifecycle.invalid('season')
        record.season = data['season']
    if 'storage_location' in data:
        record.storage_location = lifecycle.text(data['storage_location'], 'storage_location', 200)
    if 'purchase_entry_id' in data:
        value = data['purchase_entry_id']
        if value in (None, ''):
            record.purchase_entry_id = None
        elif type(value) is not int or Entry.query.filter_by(id=value, user_id=user.id, vehicle_id=record.vehicle_id).first() is None:
            lifecycle.invalid('purchase_entry_id')
        else:
            record.purchase_entry_id = value
    if 'rotation_interval' in data:
        record.rotation_interval = lifecycle.number(data['rotation_interval'], 'rotation_interval')
        if record.rotation_interval == 0:
            lifecycle.invalid('rotation_interval')
    if 'tread_unit' in data:
        if data['tread_unit'] not in lifecycle.TREAD_UNITS:
            lifecycle.invalid('tread_unit')
        record.tread_unit = data['tread_unit']
    if 'tread_threshold' in data:
        record.tread_threshold = lifecycle.number(data['tread_threshold'], 'tread_threshold', 100)


def saved(record, status=200):
    if record.id:
        DueDismissal.query.filter(DueDismissal.user_id == record.user_id,
            DueDismissal.kind.in_(['tire_rotation', 'tire_tread']), DueDismissal.ref_id == record.id).delete(synchronize_session=False)
    record.updated_at = utc_naive_now()
    commit_mutation()
    return jsonify(record.to_dict()), status


@tires_bp.route('', methods=['GET'])
@token_required
def list_sets(user):
    vehicle = Vehicle.query.filter_by(id=request.args.get('vehicle_id', type=int), user_id=user.id).first_or_404()
    return jsonify({'sets': [s.to_dict() for s in TireSet.query.filter_by(user_id=user.id, vehicle_id=vehicle.id).order_by(TireSet.id)]})


@tires_bp.route('/<int:set_id>', methods=['GET'])
@token_required
def get_set(user, set_id):
    return jsonify(owned(user, set_id).to_dict())


@tires_bp.route('', methods=['POST'])
@token_required
@mutation_endpoint(TireSet)
def create_set(user):
    data = request.get_json() or {}
    vehicle = vehicle_for_write(user, data.get('vehicle_id'))
    record = TireSet(user_id=user.id, vehicle_id=vehicle.id)
    settings(record, data, user)
    if not record.name:
        lifecycle.invalid('name')
    identifiers = data.get('tires')
    if not isinstance(identifiers, list) or len(identifiers) != 4:
        lifecycle.invalid('tires')
    identifiers = [lifecycle.text(v, 'tires', 60, True) for v in identifiers]
    if len(set(identifiers)) != 4:
        lifecycle.invalid('tires')
    record.tires = [Tire(user_id=user.id, vehicle_id=vehicle.id, identifier=v) for v in identifiers]
    db.session.add(record)
    return saved(record, 201)


@tires_bp.route('/<int:set_id>', methods=['PUT'])
@token_required
@mutation_endpoint(TireSet, 'set_id')
def update_set(user, set_id):
    record = owned(user, set_id)
    vehicle_for_write(user, record.vehicle_id)
    settings(record, request.get_json() or {}, user)
    return saved(record)


@tires_bp.route('/<int:set_id>', methods=['DELETE'])
@token_required
@mutation_endpoint(TireSet, 'set_id')
def delete_set(user, set_id):
    record = owned(user, set_id)
    vehicle_for_write(user, record.vehicle_id)
    if record.events or record.readings:
        return jsonify({'error': 'Keep sets with recorded history. Correct the history instead.', 'message_key': 'tires.keepHistory'}), 409
    db.session.delete(record)
    commit_mutation()
    return jsonify({'deleted': True})


@tires_bp.route('/<int:set_id>/events', methods=['POST'])
@token_required
@mutation_endpoint(TireSet, 'set_id')
def add_event(user, set_id):
    record = owned(user, set_id)
    vehicle_for_write(user, record.vehicle_id)
    data = request.get_json() or {}
    event = FitmentEvent(user_id=user.id, vehicle_id=record.vehicle_id,
        kind=data.get('kind'), date=lifecycle.day(data.get('date')),
        odometer=lifecycle.number(data.get('odometer'), 'odometer'), positions=data.get('positions'))
    if event.kind not in ('install', 'rotate', 'remove') or not isinstance(event.positions, dict):
        lifecycle.invalid('kind')
    record.events.append(event)
    db.session.flush()
    lifecycle.validate_vehicle(record.vehicle_id)
    return saved(record, 201)


@tires_bp.route('/<int:set_id>/events/<int:event_id>', methods=['PUT', 'DELETE'])
@token_required
@mutation_endpoint(TireSet, 'set_id')
def correct_event(user, set_id, event_id):
    record = owned(user, set_id)
    vehicle_for_write(user, record.vehicle_id)
    event = FitmentEvent.query.filter_by(id=event_id, tire_set_id=set_id, user_id=user.id).first_or_404()
    if request.method == 'DELETE':
        if event.id != record.events[-1].id:
            lifecycle.invalid('event_id')
        record.events.remove(event)
    else:
        data = request.get_json() or {}
        event.date = lifecycle.day(data.get('date'))
        event.odometer = lifecycle.number(data.get('odometer'), 'odometer')
    db.session.flush()
    lifecycle.validate_vehicle(record.vehicle_id)
    return saved(record)


@tires_bp.route('/<int:set_id>/readings', methods=['POST'])
@token_required
@mutation_endpoint(TireSet, 'set_id')
def add_reading(user, set_id):
    record = owned(user, set_id)
    vehicle_for_write(user, record.vehicle_id)
    data = request.get_json() or {}
    if type(data.get('tire_id')) is not int or data['tire_id'] not in {t.id for t in record.tires}:
        lifecycle.invalid('tire_id')
    if data.get('unit') not in lifecycle.TREAD_UNITS:
        lifecycle.invalid('unit')
    record.readings.append(TreadReading(user_id=user.id, vehicle_id=record.vehicle_id,
        tire_id=data['tire_id'], date=lifecycle.day(data.get('date')),
        depth=lifecycle.number(data.get('depth'), 'depth', 100, optional=False), unit=data['unit']))
    return saved(record, 201)


@tires_bp.route('/<int:set_id>/readings/<int:reading_id>', methods=['DELETE'])
@token_required
@mutation_endpoint(TireSet, 'set_id')
def delete_reading(user, set_id, reading_id):
    record = owned(user, set_id)
    vehicle_for_write(user, record.vehicle_id)
    reading = TreadReading.query.filter_by(id=reading_id, tire_set_id=set_id, user_id=user.id).first_or_404()
    record.readings.remove(reading)
    return saved(record)
