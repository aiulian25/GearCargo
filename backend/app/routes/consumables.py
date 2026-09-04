"""
GearCargo - Consumable Entry Routes (tires, battery, wipers, filters, …)
"""

from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.orm import selectinload

from app import db
from app.models import Vehicle, ConsumableEntry
from app.models.consumable import CONSUMABLE_TYPES
from app.routes.auth import token_required
from app.utils.entryparse import (
    InvalidFieldError,
    invalid_field_response,
    parse_amount,
    parse_currency_code,
    parse_optional_date,
    parse_optional_int,
)

consumables_bp = Blueprint('consumables', __name__)

# Integer columns a client may address, by request key (R4-11).
_INTEGER_FIELDS = ('odometer', 'install_odometer', 'expected_lifespan_km',
                   'expected_lifespan_months', 'warranty_months', 'quantity')


@consumables_bp.route('', methods=['GET'])
@token_required
def get_consumable_entries(current_user):
    """List consumable entries (optionally filtered by vehicle), newest first.

    Includes a wear estimate computed against the vehicle's current mileage.
    """
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = max(1, min(request.args.get('per_page', 50, type=int), 100))

    query = ConsumableEntry.query.join(Vehicle).filter(Vehicle.user_id == current_user.id)
    if vehicle_id:
        query = query.filter(ConsumableEntry.vehicle_id == vehicle_id)

    # R4-15: batch the attachments the rows serialize — one query for the
    # page instead of one per entry.
    entries = query.options(selectinload(ConsumableEntry.attachments)) \
        .order_by(ConsumableEntry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Cache vehicle current_mileage so wear estimates don't trigger N+1 lookups.
    mileage_by_vehicle = {}

    def mileage_for(vid):
        if vid not in mileage_by_vehicle:
            v = db.session.get(Vehicle, vid)
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

    # Every parse below raises InvalidFieldError, caught once — malformed input
    # used to escape as a 500 (R4-10) or reach a Numeric/Integer column raw
    # (R4-11).
    try:
        entry_date = parse_optional_date(data.get('date')) or datetime.now(timezone.utc).date()
        install_date = parse_optional_date(data.get('install_date')) or entry_date
        install_odometer = parse_optional_int(data.get('install_odometer'),
                                              'Odometer must be a number')
        odometer = parse_optional_int(data.get('odometer'), 'Odometer must be a number')
        quantity = parse_optional_int(data.get('quantity'), 'Quantity must be a number')
        expected_lifespan_km = parse_optional_int(data.get('expected_lifespan_km'),
                                                  'Expected lifespan must be a number')
        expected_lifespan_months = parse_optional_int(data.get('expected_lifespan_months'),
                                                      'Expected lifespan must be a number')
        warranty_months = parse_optional_int(data.get('warranty_months'),
                                             'Warranty months must be a number')
        amount = parse_amount(data.get('amount') or 0)
        currency = parse_currency_code(
            data.get('currency') or vehicle_default_currency(current_user))
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    # Default install_odometer to the entry odometer when not given separately.
    if install_odometer is None:
        install_odometer = odometer

    entry = ConsumableEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        amount=amount,
        currency=currency,
        title=data.get('title') or None,
        description=data.get('description'),
        notes=data.get('notes'),
        odometer=odometer,
        consumable_type=consumable_type,
        brand=(data.get('brand') or None),
        quantity=quantity or 1,
        install_date=install_date,
        install_odometer=install_odometer,
        expected_lifespan_km=expected_lifespan_km,
        expected_lifespan_months=expected_lifespan_months,
        warranty_months=warranty_months,
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
    vehicle = db.session.get(Vehicle, entry.vehicle_id)
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

    # Parsed up front so a rejected field cannot leave the earlier ones already
    # applied — this handler used to assign field by field as it went (R4-11).
    try:
        parsed_columns = {}
        for int_field in _INTEGER_FIELDS:
            if int_field in data:
                parsed_columns[int_field] = parse_optional_int(data[int_field])
        if 'amount' in data:
            parsed_columns['amount'] = parse_amount(data.get('amount') or 0)
        if 'currency' in data:
            # A blank code clears it, as before; a non-blank one has to be a
            # real 3-letter code — the column is String(3).
            parsed_columns['currency'] = (parse_currency_code(data['currency'])
                                          if data['currency'] else None)
        # entries.date is NOT NULL, so a falsy value leaves it alone;
        # install_date is nullable and stays clearable.
        if data.get('date'):
            parsed_columns['date'] = parse_optional_date(data['date'])
        if 'install_date' in data:
            parsed_columns['install_date'] = parse_optional_date(data['install_date'])
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    if 'consumable_type' in data:
        entry.consumable_type = ctype

    # Simple scalar fields
    for field in ('title', 'description', 'notes', 'brand'):
        if field in data:
            setattr(entry, field, data[field] or None)

    for column, value in parsed_columns.items():
        setattr(entry, column, value)

    db.session.commit()
    vehicle = db.session.get(Vehicle, entry.vehicle_id)
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
