"""
GearCargo - Repair Entry Routes
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func, case

from app import db
from app.models import Vehicle, RepairEntry
from app.routes.auth import token_required

repairs_bp = Blueprint('repairs', __name__)

# Known repair-type values. Module-level so BOTH create and update validate
# against the same set (L10) — keeping by_type stats and the health endpoint's
# REPAIR_TYPE_TO_COMPONENTS matching consistent between POST and PUT.
VALID_REPAIR_TYPES = {
    'engine', 'transmission', 'brakes', 'suspension', 'electrical',
    'exhaust', 'cooling', 'fuel_system', 'steering', 'body',
    'interior', 'ac_heating', 'tires_wheels', 'clutch', 'drivetrain',
    'windshield', 'lights', 'oil_change', 'filters', 'battery',
    'turbo', 'timing_belt', 'differential', 'other'
}


def _opt_int(value):
    """Coerce an optional numeric field to int, treating ''/invalid as None."""
    try:
        return int(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


@repairs_bp.route('', methods=['GET'])
@token_required
def get_repair_entries(current_user):
    """Get repair entries."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = RepairEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(RepairEntry.vehicle_id == vehicle_id)
    
    entries = query.order_by(RepairEntry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'entries': [e.to_dict() for e in entries.items],
        'total': entries.total,
        'pages': entries.pages,
        'current_page': page,
    })


@repairs_bp.route('', methods=['POST'])
@token_required
def create_repair_entry(current_user):
    """Create a new repair entry."""
    data = request.get_json()
    
    vehicle = Vehicle.query.filter_by(
        id=data.get('vehicle_id'),
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    if not data.get('repair_type') and not data.get('repair_types'):
        return jsonify({'error': 'Repair type is required'}), 400
    
    # Support multi-select repair_types (array) and legacy repair_type (string)
    repair_types_list = data.get('repair_types') or []
    if not isinstance(repair_types_list, list):
        repair_types_list = [repair_types_list]
    if not repair_types_list and data.get('repair_type'):
        repair_types_list = [data['repair_type']]
    
    # Validate repair types — only allow known values (module-level set).
    repair_types_list = [rt for rt in repair_types_list if rt in VALID_REPAIR_TYPES]
    if not repair_types_list:
        return jsonify({'error': 'At least one valid repair type is required'}), 400
    
    primary_type = repair_types_list[0]
    
    # Parse date - support both 'date' and 'entry_date' field names
    entry_date = datetime.now(timezone.utc).date()
    if data.get('date'):
        entry_date = datetime.fromisoformat(data['date'].replace('Z', '+00:00')).date()
    elif data.get('entry_date'):
        entry_date = datetime.fromisoformat(data['entry_date'].replace('Z', '+00:00')).date()
    
    entry = RepairEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        odometer=data.get('mileage') or data.get('odometer'),
        amount=data.get('total_cost') or data.get('cost') or data.get('amount', 0),
        currency=data.get('currency') or current_user.currency or 'EUR',
        title=', '.join(repair_types_list),
        description=data.get('description'),
        repair_type=primary_type,
        repair_types=repair_types_list,
        diagnosis=data.get('diagnosis'),
        symptoms=data.get('symptoms'),
        root_cause=data.get('root_cause'),
        provider=data.get('shop_name') or data.get('provider_name') or data.get('provider'),
        garage_name=data.get('shop_name') or data.get('garage_name') or data.get('provider_name'),
        garage_address=data.get('provider_location') or data.get('garage_address'),
        labor_hours=data.get('labor_hours'),
        labor_cost=data.get('labor_cost'),
        parts_cost=data.get('parts_cost'),
        parts_replaced=data.get('parts_replaced'),
        severity=data.get('severity', 'medium'),
        under_warranty=data.get('warranty_covered') or data.get('under_warranty', False),
        warranty_months=_opt_int(data.get('warranty_months')),
        warranty_km=_opt_int(data.get('warranty_km')),
        notes=data.get('notes'),
    )
    
    if entry.odometer and entry.odometer > vehicle.current_mileage:
        vehicle.current_mileage = entry.odometer
    
    db.session.add(entry)
    db.session.commit()

    # Auto-sync to calendar if enabled
    if current_user.calendar_enabled:
        try:
            from app.services.calendar_service import sync_entry_to_calendar
            sync_entry_to_calendar(current_user, 'repair', entry, 'create')
        except Exception as e:
            current_app.logger.warning(f"Calendar sync failed for repair: {e}")

    return jsonify({
        'message': 'Repair entry created',
        'entry': entry.to_dict()
    }), 201


@repairs_bp.route('/<int:entry_id>', methods=['GET'])
@token_required
def get_repair_entry(current_user, entry_id):
    """Get a specific repair entry."""
    entry = RepairEntry.query.join(Vehicle).filter(
        RepairEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    return jsonify(entry.to_dict())


@repairs_bp.route('/<int:entry_id>', methods=['PUT'])
@token_required
def update_repair_entry(current_user, entry_id):
    """Update a repair entry."""
    entry = RepairEntry.query.join(Vehicle).filter(
        RepairEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    data = request.get_json()
    
    # Handle multi-select repair_types. L10: validate on update exactly as create
    # does — filter to known values and reject if the client sent a selection but
    # none are valid, so PUT can't store arbitrary strings that corrupt by_type
    # stats and REPAIR_TYPE_TO_COMPONENTS matching. Omitting types (or sending an
    # empty list) leaves the existing types untouched, as before.
    incoming_types = None
    if 'repair_types' in data:
        incoming_types = data['repair_types']
        if not isinstance(incoming_types, list):
            incoming_types = [incoming_types]
    elif 'repair_type' in data and data['repair_type']:
        incoming_types = [data['repair_type']]

    if incoming_types:
        valid_types = [rt for rt in incoming_types if rt in VALID_REPAIR_TYPES]
        if not valid_types:
            return jsonify({'error': 'At least one valid repair type is required'}), 400
        entry.repair_types = valid_types
        entry.repair_type = valid_types[0]
        entry.title = ', '.join(valid_types)

    # F18 — request keys mapped to the REAL model columns. Aliases first,
    # canonical names last so the canonical value wins when both are sent.
    # (is_recurring / insurance_* / provider_phone have no RepairEntry columns.)
    field_aliases = {
        'entry_date': 'date', 'date': 'date',
        'mileage': 'odometer', 'odometer': 'odometer',
        'description': 'description',
        'diagnosis': 'diagnosis', 'symptoms': 'symptoms', 'root_cause': 'root_cause',
        'provider_name': 'provider', 'shop_name': 'provider', 'provider': 'provider',
        'provider_location': 'garage_address', 'garage_address': 'garage_address',
        'parts_replaced': 'parts_replaced',
        'labor_hours': 'labor_hours',
        'labor_cost': 'labor_cost', 'parts_cost': 'parts_cost',
        'currency': 'currency',
        'severity': 'severity',
        'notes': 'notes',
    }

    for key, column in field_aliases.items():
        if key not in data:
            continue
        value = data[key]
        if column == 'date':
            if value:
                entry.date = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
        elif column == 'odometer':
            entry.odometer = _opt_int(value)
        else:
            setattr(entry, column, value)

    # The shop field names both the provider and the garage (mirrors create).
    if data.get('shop_name') or data.get('provider_name'):
        entry.garage_name = data.get('shop_name') or data.get('provider_name')

    # Recalculate amount (mirrors update_service_entry — was missing here).
    if 'cost' in data or 'total_cost' in data:
        entry.amount = data.get('total_cost') or data.get('cost') or 0
    elif 'labor_cost' in data or 'parts_cost' in data:
        labor = float(entry.labor_cost or 0)
        parts = float(entry.parts_cost or 0)
        entry.amount = labor + parts

    # Mirror create's mileage bump — vehicle mileage only ever increases.
    if entry.odometer:
        vehicle = db.session.get(Vehicle, entry.vehicle_id)
        if vehicle and entry.odometer > (vehicle.current_mileage or 0):
            vehicle.current_mileage = entry.odometer

    # F2 — warranty fields, mapped to the real columns.
    if 'warranty_covered' in data or 'under_warranty' in data:
        entry.under_warranty = bool(data.get('warranty_covered') or data.get('under_warranty'))
    if 'warranty_months' in data:
        entry.warranty_months = _opt_int(data['warranty_months'])
    if 'warranty_km' in data:
        entry.warranty_km = _opt_int(data['warranty_km'])

    db.session.commit()

    return jsonify({
        'message': 'Repair entry updated',
        'entry': entry.to_dict()
    })


@repairs_bp.route('/<int:entry_id>', methods=['DELETE'])
@token_required
def delete_repair_entry(current_user, entry_id):
    """Delete a repair entry."""
    entry = RepairEntry.query.join(Vehicle).filter(
        RepairEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    db.session.delete(entry)
    db.session.commit()
    
    return jsonify({'message': 'Repair entry deleted'})


@repairs_bp.route('/stats', methods=['GET'])
@token_required
def get_repair_stats(current_user):
    """Get repair statistics."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    # M9: DB aggregation. The scalar totals and the severity breakdown are pure
    # grouped SQL; only `by_type` still scans rows because it fans one repair out
    # over a JSON array column (`repair_types`), which isn't portably groupable —
    # and even that fetches ONLY the three columns it needs, not full ORM rows.
    filters = [Vehicle.user_id == current_user.id]
    if vehicle_id:
        filters.append(RepairEntry.vehicle_id == vehicle_id)

    entry_count, total_cost, warranty_savings = (
        db.session.query(
            func.count(RepairEntry.id),
            func.coalesce(func.sum(RepairEntry.amount), 0),
            # 'Savings' = cost of repairs covered by an existing warranty.
            # case(...) rather than an aggregate FILTER for SQLite/Postgres portability.
            func.coalesce(
                func.sum(case((RepairEntry.under_warranty.is_(True), RepairEntry.amount), else_=0)), 0
            ),
        )
        .join(Vehicle).filter(*filters)
        .one()
    )
    # RepairEntry has no insurance columns — keep the response shape stable.
    insurance_claims = 0.0

    # By severity — grouped in SQL; NULL/'' → 'medium', unknown severities dropped
    # (only the four fixed buckets are counted), exactly as before.
    by_severity = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
    for sev_raw, cnt in (
        db.session.query(RepairEntry.severity, func.count(RepairEntry.id))
        .join(Vehicle).filter(*filters)
        .group_by(RepairEntry.severity)
        .all()
    ):
        severity = sev_raw or 'medium'
        if severity in by_severity:
            by_severity[severity] += cnt

    # By type — one repair can list multiple `repair_types` (JSON array) and each
    # gets the full entry amount, so this fans out per row. Fetch only the 3
    # needed columns (not entities) and reproduce the original loop verbatim.
    by_type = {}
    for repair_types, repair_type, amount in (
        db.session.query(RepairEntry.repair_types, RepairEntry.repair_type, RepairEntry.amount)
        .join(Vehicle).filter(*filters)
        .all()
    ):
        types = repair_types or ([repair_type] if repair_type else ['other'])
        for rtype in types:
            if rtype not in by_type:
                by_type[rtype] = {'count': 0, 'cost': 0}
            by_type[rtype]['count'] += 1
            by_type[rtype]['cost'] += float(amount or 0)

    return jsonify({
        'total_cost': float(total_cost or 0),
        'entry_count': entry_count,
        'warranty_savings': float(warranty_savings or 0),
        'insurance_claims': float(insurance_claims),
        'by_severity': by_severity,
        'by_type': by_type,
    })
