"""
GearCargo - Service Entry Routes
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app

from app import db
from app.models import Vehicle, ServiceEntry
from app.routes.auth import token_required

services_bp = Blueprint('services', __name__)


@services_bp.route('', methods=['GET'])
@token_required
def get_service_entries(current_user):
    """Get service entries."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = ServiceEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(ServiceEntry.vehicle_id == vehicle_id)
    
    entries = query.order_by(ServiceEntry.date.desc()).paginate(
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
    VALID_SERVICE_TYPES = {
        'oil_change', 'tire_rotation', 'brake_service', 'air_filter', 'cabin_filter',
        'spark_plugs', 'transmission', 'coolant', 'timing_belt', 'inspection',
        'full_service', 'other',
    }
    
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
    
    # Parse date - support both 'date' and 'entry_date' field names
    entry_date = datetime.now(timezone.utc).date()
    if data.get('date'):
        entry_date = datetime.fromisoformat(data['date'].replace('Z', '+00:00')).date()
    elif data.get('entry_date'):
        entry_date = datetime.fromisoformat(data['entry_date'].replace('Z', '+00:00')).date()
    
    # Parse next service date
    next_due_date = None
    if data.get('next_service_date'):
        next_due_date = datetime.fromisoformat(data['next_service_date'].replace('Z', '+00:00')).date()
    elif data.get('next_due_date'):
        next_due_date = datetime.fromisoformat(data['next_due_date'].replace('Z', '+00:00')).date()
    
    # Parse warranty expiry
    warranty_expires = None
    if data.get('warranty_until'):
        warranty_expires = datetime.fromisoformat(data['warranty_until'].replace('Z', '+00:00')).date()
    elif data.get('warranty_expires'):
        warranty_expires = datetime.fromisoformat(data['warranty_expires'].replace('Z', '+00:00')).date()
    
    # Calculate amount: use explicit total_cost/cost, or sum labor_cost + parts_cost
    amount = data.get('total_cost') or data.get('cost') or data.get('amount')
    if amount is None or amount == 0:
        labor = float(data.get('labor_cost') or 0)
        parts = float(data.get('parts_cost') or 0)
        amount = labor + parts
    
    entry = ServiceEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        odometer=data.get('mileage') or data.get('odometer'),
        amount=amount,
        title=', '.join(service_types_list),
        description=data.get('description'),
        service_type=service_types_list[0],
        service_types=service_types_list,
        provider=data.get('shop_name') or data.get('provider_name') or data.get('provider'),
        garage_name=data.get('shop_name') or data.get('garage_name') or data.get('provider_name'),
        garage_address=data.get('provider_location') or data.get('garage_address'),
        garage_phone=data.get('provider_phone') or data.get('garage_phone'),
        labor_cost=data.get('labor_cost'),
        parts_cost=data.get('parts_cost'),
        parts_used=data.get('parts_replaced') or data.get('parts_used'),
        next_due_mileage=data.get('next_service_mileage') or data.get('next_due_mileage'),
        next_due_date=next_due_date,
        warranty_expires=warranty_expires,
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
    VALID_SERVICE_TYPES = {
        'oil_change', 'tire_rotation', 'brake_service', 'air_filter', 'cabin_filter',
        'spark_plugs', 'transmission', 'coolant', 'timing_belt', 'inspection',
        'full_service', 'other',
    }
    
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
    
    allowed = ['entry_date', 'mileage', 'cost', 'description',
               'provider_name', 'provider_location', 'provider_phone',
               'parts_replaced', 'labor_cost', 'parts_cost',
               'next_service_mileage', 'next_service_date', 'warranty_until', 'notes']
    
    for field in allowed:
        if field in data:
            if field in ['entry_date', 'next_service_date', 'warranty_until'] and data[field]:
                setattr(entry, field, datetime.fromisoformat(data[field]))
            else:
                setattr(entry, field, data[field])
    
    # Recalculate amount from labor_cost + parts_cost if either was updated
    # or if cost/total_cost was explicitly provided
    if 'cost' in data or 'total_cost' in data:
        entry.amount = data.get('total_cost') or data.get('cost') or 0
    elif 'labor_cost' in data or 'parts_cost' in data:
        labor = float(entry.labor_cost or 0)
        parts = float(entry.parts_cost or 0)
        entry.amount = labor + parts
    
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
        ServiceEntry.next_service_date.isnot(None),
        ServiceEntry.next_service_date >= datetime.now(timezone.utc)
    )
    
    if vehicle_id:
        query = query.filter(ServiceEntry.vehicle_id == vehicle_id)
    
    entries = query.order_by(ServiceEntry.next_service_date.asc()).limit(10).all()
    
    return jsonify({
        'entries': [e.to_dict() for e in entries]
    })


@services_bp.route('/stats', methods=['GET'])
@token_required
def get_service_stats(current_user):
    """Get service statistics."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    query = ServiceEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(ServiceEntry.vehicle_id == vehicle_id)
    
    entries = query.all()
    
    total_cost = sum(e.cost or 0 for e in entries)
    total_labor = sum(e.labor_cost or 0 for e in entries)
    total_parts = sum(e.parts_cost or 0 for e in entries)
    
    # Service types breakdown
    by_type = {}
    for entry in entries:
        stype = entry.service_type or 'other'
        if stype not in by_type:
            by_type[stype] = {'count': 0, 'cost': 0}
        by_type[stype]['count'] += 1
        by_type[stype]['cost'] += float(entry.cost or 0)
    
    return jsonify({
        'total_cost': float(total_cost),
        'total_labor_cost': float(total_labor),
        'total_parts_cost': float(total_parts),
        'entry_count': len(entries),
        'by_type': by_type,
    })
