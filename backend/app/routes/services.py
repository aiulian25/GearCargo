"""
GearCargo - Service Entry Routes
"""

from datetime import datetime, date, timezone
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app import db
from app.models import Vehicle, ServiceEntry
from app.models.service import VALID_SERVICE_TYPES
from app.routes.auth import token_required
from app.utils.entryparse import (
    InvalidFieldError,
    invalid_field_response,
    parse_amount,
    parse_currency_code,
    parse_iso_date,
    parse_optional_amount,
    parse_optional_int,
)
from app.utils.timeutils import utc_today

services_bp = Blueprint('services', __name__)

# Typed columns, by the request key that addresses them. Kept apart from the
# free-text aliases in update_service_entry because every one of them needs
# coercing before it reaches the column (R4-10 / R4-11). Aliases first,
# canonical name last, so the canonical value wins when both are sent.
_DATE_FIELDS = {
    'entry_date': 'date', 'date': 'date',
    'next_service_date': 'next_due_date', 'next_due_date': 'next_due_date',
    'warranty_until': 'warranty_expires', 'warranty_expires': 'warranty_expires',
}
_INTEGER_FIELDS = {
    'mileage': 'odometer', 'odometer': 'odometer',
    'next_service_mileage': 'next_due_mileage', 'next_due_mileage': 'next_due_mileage',
    'warranty_months': 'warranty_months',
    'warranty_km': 'warranty_km',
}
_AMOUNT_FIELDS = {
    'labor_hours': 'labor_hours',
    'labor_cost': 'labor_cost',
    'parts_cost': 'parts_cost',
}

# entries.date is NOT NULL — a falsy value leaves it alone instead of clearing it.
_NON_CLEARABLE_DATE = 'date'


@services_bp.route('', methods=['GET'])
@token_required
def get_service_entries(current_user):
    """Get service entries."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = max(1, min(request.args.get('per_page', 20, type=int), 100))
    
    query = ServiceEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(ServiceEntry.vehicle_id == vehicle_id)
    
    # R4-15: batch the attachments the rows serialize — one query for the
    # page instead of one per entry.
    entries = query.options(selectinload(ServiceEntry.attachments)) \
        .order_by(ServiceEntry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'entries': [e.to_dict() for e in entries.items],
        'total': entries.total,
        'pages': entries.pages,
        'current_page': page,
    })


@services_bp.route('', methods=['POST'])
@token_required
def create_service_entry(current_user):
    """Create a new service entry."""
    data = request.get_json()
    
    vehicle = Vehicle.query.filter_by(
        id=data.get('vehicle_id'),
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    # Handle multi-select service_types (array) with legacy service_type (string) fallback
    service_types_list = data.get('service_types') or []
    if not isinstance(service_types_list, list):
        service_types_list = [service_types_list]
    
    # Fallback to legacy single service_type
    if not service_types_list and data.get('service_type'):
        service_types_list = [data['service_type']]
    
    # Validate: filter to known types, require at least one
    service_types_list = [t for t in service_types_list if t in VALID_SERVICE_TYPES]
    if not service_types_list:
        return jsonify({'error': 'At least one valid service type is required'}), 400
    
    # Every parse below raises InvalidFieldError, caught once — malformed input
    # used to escape as a 500 (R4-10) or reach a Numeric/Integer column raw
    # (R4-11). Field names support both the form's and the model's spelling.
    try:
        entry_date = datetime.now(timezone.utc).date()
        if data.get('date'):
            entry_date = parse_iso_date(data['date'])
        elif data.get('entry_date'):
            entry_date = parse_iso_date(data['entry_date'])

        next_due_date = None
        if data.get('next_service_date'):
            next_due_date = parse_iso_date(data['next_service_date'])
        elif data.get('next_due_date'):
            next_due_date = parse_iso_date(data['next_due_date'])

        warranty_expires = None
        if data.get('warranty_until'):
            warranty_expires = parse_iso_date(data['warranty_until'])
        elif data.get('warranty_expires'):
            warranty_expires = parse_iso_date(data['warranty_expires'])

        odometer = parse_optional_int(data.get('mileage') or data.get('odometer'),
                                      'Odometer must be a number')
        next_due_mileage = parse_optional_int(
            data.get('next_service_mileage') or data.get('next_due_mileage'),
            'Next service mileage must be a number')
        warranty_months = parse_optional_int(data.get('warranty_months'),
                                             'Warranty months must be a number')
        warranty_km = parse_optional_int(data.get('warranty_km'),
                                         'Warranty distance must be a number')
        labor_hours = parse_optional_amount(data.get('labor_hours'),
                                            'Labour hours must be a number')
        labor_cost = parse_optional_amount(data.get('labor_cost'))
        parts_cost = parse_optional_amount(data.get('parts_cost'))

        currency = parse_currency_code(
            data.get('currency') or current_user.currency or 'EUR')

        # Explicit total wins; otherwise the parts and labour add up to it.
        raw_amount = data.get('total_cost') or data.get('cost') or data.get('amount')
        amount = parse_amount(raw_amount) if raw_amount else 0.0
        if not amount:
            amount = (labor_cost or 0) + (parts_cost or 0)
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status
    
    entry = ServiceEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        odometer=odometer,
        amount=amount,
        currency=currency,
        title=', '.join(service_types_list),
        description=data.get('description'),
        service_type=service_types_list[0],
        service_types=service_types_list,
        provider=data.get('shop_name') or data.get('provider_name') or data.get('provider'),
        garage_name=data.get('shop_name') or data.get('garage_name') or data.get('provider_name'),
        garage_address=data.get('provider_location') or data.get('garage_address'),
        garage_phone=data.get('provider_phone') or data.get('garage_phone'),
        work_order_number=data.get('work_order_number'),
        labor_hours=labor_hours,
        labor_cost=labor_cost,
        parts_cost=parts_cost,
        parts_used=data.get('parts_replaced') or data.get('parts_used'),
        next_due_mileage=next_due_mileage,
        next_due_date=next_due_date,
        warranty_expires=warranty_expires,
        warranty_months=warranty_months,
        warranty_km=warranty_km,
        notes=data.get('notes'),
    )
    
    if entry.odometer and entry.odometer > (vehicle.current_mileage or 0):
        vehicle.current_mileage = entry.odometer
    
    db.session.add(entry)
    db.session.commit()
    
    # Auto-sync to calendar if enabled
    if current_user.calendar_enabled:
        try:
            from app.services.calendar_service import sync_entry_to_calendar
            sync_entry_to_calendar(current_user, 'service', entry, 'create')
        except Exception as e:
            current_app.logger.warning(f"Calendar sync failed for service: {e}")
    
    return jsonify({
        'message': 'Service entry created',
        'entry': entry.to_dict()
    }), 201


@services_bp.route('/<int:entry_id>', methods=['GET'])
@token_required
def get_service_entry(current_user, entry_id):
    """Get a specific service entry."""
    entry = ServiceEntry.query.join(Vehicle).filter(
        ServiceEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    return jsonify(entry.to_dict())


@services_bp.route('/<int:entry_id>', methods=['PUT'])
@token_required
def update_service_entry(current_user, entry_id):
    """Update a service entry."""
    entry = ServiceEntry.query.join(Vehicle).filter(
        ServiceEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    data = request.get_json()
    
    # Handle multi-select service_types update
    if 'service_types' in data or 'service_type' in data:
        service_types_list = data.get('service_types') or []
        if not isinstance(service_types_list, list):
            service_types_list = [service_types_list]
        if not service_types_list and data.get('service_type'):
            service_types_list = [data['service_type']]
        service_types_list = [t for t in service_types_list if t in VALID_SERVICE_TYPES]
        if service_types_list:
            entry.service_types = service_types_list
            entry.service_type = service_types_list[0]
            entry.title = ', '.join(service_types_list)
    
    # F18 — request keys mapped to the REAL model columns. Aliases first,
    # canonical names last so the canonical value wins when both are sent.
    # (Dates, integers and amounts live in the typed maps at the top of this
    # module — none of them may be assigned raw.)
    field_aliases = {
        'description': 'description',
        'provider_name': 'provider', 'provider': 'provider',
        'shop_name': 'garage_name', 'garage_name': 'garage_name',
        'provider_location': 'garage_address', 'garage_address': 'garage_address',
        'provider_phone': 'garage_phone', 'garage_phone': 'garage_phone',
        'parts_replaced': 'parts_used', 'parts_used': 'parts_used',
        'work_order_number': 'work_order_number',
        'notes': 'notes',
    }

    # Parsed up front so a rejected field cannot leave the earlier ones already
    # applied — the loop below used to mutate the entry as it went (R4-11).
    try:
        parsed_columns = {}
        for key, column in _DATE_FIELDS.items():
            if key not in data:
                continue
            if data[key]:
                parsed_columns[column] = parse_iso_date(data[key])
            elif column != _NON_CLEARABLE_DATE:
                parsed_columns[column] = None
        for key, column in _INTEGER_FIELDS.items():
            if key in data:
                parsed_columns[column] = parse_optional_int(data[key])
        for key, column in _AMOUNT_FIELDS.items():
            if key in data:
                parsed_columns[column] = parse_optional_amount(data[key])
        if 'currency' in data:
            parsed_columns['currency'] = parse_currency_code(data['currency'])
        if 'cost' in data or 'total_cost' in data:
            raw_amount = data.get('total_cost') or data.get('cost')
            parsed_columns['amount'] = parse_amount(raw_amount) if raw_amount else 0.0
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    for key, column in field_aliases.items():
        if key in data:
            setattr(entry, column, data[key])

    for column, value in parsed_columns.items():
        setattr(entry, column, value)

    # Mirror create's mileage bump — vehicle mileage only ever increases.
    if entry.odometer:
        vehicle = db.session.get(Vehicle, entry.vehicle_id)
        if vehicle and entry.odometer > (vehicle.current_mileage or 0):
            vehicle.current_mileage = entry.odometer

    # No explicit total sent, but the parts or labour changed — the two add up
    # to the amount. Reads the values applied just above.
    amount_was_sent = 'amount' in parsed_columns
    labor_or_parts_changed = 'labor_cost' in data or 'parts_cost' in data
    if not amount_was_sent and labor_or_parts_changed:
        entry.amount = float(entry.labor_cost or 0) + float(entry.parts_cost or 0)

    db.session.commit()
    
    return jsonify({
        'message': 'Service entry updated',
        'entry': entry.to_dict()
    })


@services_bp.route('/<int:entry_id>', methods=['DELETE'])
@token_required
def delete_service_entry(current_user, entry_id):
    """Delete a service entry."""
    entry = ServiceEntry.query.join(Vehicle).filter(
        ServiceEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    db.session.delete(entry)
    db.session.commit()
    
    return jsonify({'message': 'Service entry deleted'})


@services_bp.route('/upcoming', methods=['GET'])
@token_required
def get_upcoming_services(current_user):
    """Get upcoming scheduled services."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    query = ServiceEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id,
        ServiceEntry.next_due_date.isnot(None),
        ServiceEntry.next_due_date >= utc_today()
    )

    if vehicle_id:
        query = query.filter(ServiceEntry.vehicle_id == vehicle_id)

    entries = query.options(selectinload(ServiceEntry.attachments)) \
        .order_by(ServiceEntry.next_due_date.asc()).limit(10).all()
    
    return jsonify({
        'entries': [e.to_dict() for e in entries]
    })


@services_bp.route('/stats', methods=['GET'])
@token_required
def get_service_stats(current_user):
    """Get service statistics."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    # M9: DB aggregation instead of loading every service row into memory.
    filters = [Vehicle.user_id == current_user.id]
    if vehicle_id:
        filters.append(ServiceEntry.vehicle_id == vehicle_id)

    entry_count, total_cost, total_labor, total_parts = (
        db.session.query(
            func.count(ServiceEntry.id),
            func.coalesce(func.sum(ServiceEntry.amount), 0),
            func.coalesce(func.sum(ServiceEntry.labor_cost), 0),
            func.coalesce(func.sum(ServiceEntry.parts_cost), 0),
        )
        .join(Vehicle).filter(*filters)
        .one()
    )

    # Service-type breakdown grouped in SQL. Post-fold NULL *and* '' into 'other'
    # exactly as the old `service_type or 'other'` did (COALESCE only catches NULL).
    by_type = {}
    for stype_raw, cnt, cost in (
        db.session.query(
            ServiceEntry.service_type,
            func.count(ServiceEntry.id),
            func.coalesce(func.sum(ServiceEntry.amount), 0),
        )
        .join(Vehicle).filter(*filters)
        .group_by(ServiceEntry.service_type)
        .all()
    ):
        stype = stype_raw or 'other'
        if stype not in by_type:
            by_type[stype] = {'count': 0, 'cost': 0}
        by_type[stype]['count'] += cnt
        by_type[stype]['cost'] += float(cost or 0)

    return jsonify({
        'total_cost': float(total_cost or 0),
        'total_labor_cost': float(total_labor or 0),
        'total_parts_cost': float(total_parts or 0),
        'entry_count': entry_count,
        'by_type': by_type,
    })
