"""
GearCargo - Consumable Entry Routes (tires, battery, wipers, filters, …)
"""

from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app

from app import db
from app.models import Vehicle, ConsumableEntry
from app.models.consumable import CONSUMABLE_TYPES
from app.routes.auth import token_required

consumables_bp = Blueprint('consumables', __name__)


def _parse_date(value):
    """Parse an ISO date/datetime string to a date, or None."""
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()


def _to_int(value):
    if value in (None, ''):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


@consumables_bp.route('', methods=['GET'])
@token_required
def get_consumable_entries(current_user):
    """List consumable entries (optionally filtered by vehicle), newest first.

    Includes a wear estimate computed against the vehicle's current mileage.
    """
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = ConsumableEntry.query.join(Vehicle).filter(Vehicle.user_id == current_user.id)
    if vehicle_id:
        query = query.filter(ConsumableEntry.vehicle_id == vehicle_id)

    entries = query.order_by(ConsumableEntry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Cache vehicle current_mileage so wear estimates don't trigger N+1 lookups.
    mileage_by_vehicle = {}

    def mileage_for(vid):
        if vid not in mileage_by_vehicle:
            v = Vehicle.query.get(vid)
            mileage_by_vehicle[vid] = v.current_mileage if v else None
        return mileage_by_vehicle[vid]

    return jsonify({
        'entries': [e.to_dict(current_mileage=mileage_for(e.vehicle_id)) for e in entries.items],
        'total': entries.total,
        'pages': entries.pages,
        'current_page': page,
    })


@consumables_bp.route('/due', methods=['GET'])
@token_required
def get_consumables_due(current_user):
    """Fleet-wide list of consumables that are worn enough to watch/replace.

    Returns every consumable across the user's NON-archived vehicles whose wear
    estimate is 'monitor' (>=70%) or 'replace' (>=100%), newest-wear first, each
    enriched with its vehicle name so a single "due" surface can label + link it.
    Ownership is enforced by scoping to the current user's vehicles.
    """
    # One query for the vehicles (name + current mileage + ownership allow-list)…
    vehicles = Vehicle.query.filter_by(user_id=current_user.id, archived=False).all()
    vinfo = {
        v.id: (
            v.name or f"{v.make or ''} {v.model or ''}".strip() or 'Vehicle',
            v.current_mileage,
        )
        for v in vehicles
    }
    if not vinfo:
        return jsonify({'items': []})

    # …and one query for all their consumables (no N+1).
    consumables = ConsumableEntry.query.filter(
        ConsumableEntry.vehicle_id.in_(list(vinfo.keys()))
    ).all()

    items = []
    for c in consumables:
        name, mileage = vinfo[c.vehicle_id]
        wear = c.wear_estimate(current_mileage=mileage)
        if wear.get('status') in ('monitor', 'replace'):
            d = c.to_dict(current_mileage=mileage)
            d['vehicle_name'] = name
            items.append(d)

    # Most-worn first (replace before monitor); unknown percents sort last.
    items.sort(key=lambda x: (x.get('wear') or {}).get('wear_percent') or 0, reverse=True)
    return jsonify({'items': items})


@consumables_bp.route('', methods=['POST'])
@token_required
def create_consumable_entry(current_user):
    """Create a consumable entry."""
    data = request.get_json() or {}

    vehicle = Vehicle.query.filter_by(id=data.get('vehicle_id'), user_id=current_user.id).first()
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404

    consumable_type = (data.get('consumable_type') or 'other').strip()
    if consumable_type not in CONSUMABLE_TYPES:
        return jsonify({'error': 'Invalid consumable type'}), 400

    entry_date = _parse_date(data.get('date')) or datetime.now(timezone.utc).date()
    install_date = _parse_date(data.get('install_date')) or entry_date
    install_odometer = _to_int(data.get('install_odometer'))
    odometer = _to_int(data.get('odometer'))
    # Default install_odometer to the entry odometer when not given separately.
    if install_odometer is None:
        install_odometer = odometer

    entry = ConsumableEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        amount=data.get('amount') or 0,
        currency=data.get('currency') or vehicle_default_currency(current_user),
        title=data.get('title') or None,
        description=data.get('description'),
        notes=data.get('notes'),
        odometer=odometer,
        consumable_type=consumable_type,
        brand=(data.get('brand') or None),
        quantity=_to_int(data.get('quantity')) or 1,
        install_date=install_date,
        install_odometer=install_odometer,
        expected_lifespan_km=_to_int(data.get('expected_lifespan_km')),
        expected_lifespan_months=_to_int(data.get('expected_lifespan_months')),
        warranty_months=_to_int(data.get('warranty_months')),
    )

    db.session.add(entry)
    db.session.commit()

    return jsonify({
        'message': 'Consumable entry created',
        'entry': entry.to_dict(current_mileage=vehicle.current_mileage),
    }), 201


def vehicle_default_currency(user):
    """Fall back to the user's preferred currency for new entries."""
    return getattr(user, 'currency', None) or 'EUR'


@consumables_bp.route('/<int:entry_id>', methods=['GET'])
@token_required
def get_consumable_entry(current_user, entry_id):
    entry = ConsumableEntry.query.join(Vehicle).filter(
        ConsumableEntry.id == entry_id,
        Vehicle.user_id == current_user.id,
    ).first()
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    vehicle = Vehicle.query.get(entry.vehicle_id)
    return jsonify(entry.to_dict(current_mileage=vehicle.current_mileage if vehicle else None))


@consumables_bp.route('/<int:entry_id>', methods=['PUT'])
@token_required
def update_consumable_entry(current_user, entry_id):
    entry = ConsumableEntry.query.join(Vehicle).filter(
        ConsumableEntry.id == entry_id,
        Vehicle.user_id == current_user.id,
    ).first()
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404

    data = request.get_json() or {}

    if 'consumable_type' in data:
        ctype = (data.get('consumable_type') or '').strip()
        if ctype not in CONSUMABLE_TYPES:
            return jsonify({'error': 'Invalid consumable type'}), 400
        entry.consumable_type = ctype

    # Simple scalar fields
    for field in ('title', 'description', 'notes', 'brand', 'currency'):
        if field in data:
            setattr(entry, field, data[field] or None)

    if 'amount' in data:
        entry.amount = data.get('amount') or 0

    for int_field in ('odometer', 'install_odometer', 'expected_lifespan_km',
                      'expected_lifespan_months', 'warranty_months', 'quantity'):
        if int_field in data:
            setattr(entry, int_field, _to_int(data[int_field]))

    if 'date' in data and data['date']:
        entry.date = _parse_date(data['date'])
    if 'install_date' in data:
        entry.install_date = _parse_date(data['install_date'])

    db.session.commit()
    vehicle = Vehicle.query.get(entry.vehicle_id)
    return jsonify({
        'message': 'Consumable entry updated',
        'entry': entry.to_dict(current_mileage=vehicle.current_mileage if vehicle else None),
    })


@consumables_bp.route('/<int:entry_id>', methods=['DELETE'])
@token_required
def delete_consumable_entry(current_user, entry_id):
    entry = ConsumableEntry.query.join(Vehicle).filter(
        ConsumableEntry.id == entry_id,
        Vehicle.user_id == current_user.id,
    ).first()
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'message': 'Consumable entry deleted'})
