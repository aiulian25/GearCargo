"""
GearCargo - Parking Entry Routes
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

from app import db
from app.models import Vehicle, ParkingEntry
from app.routes.auth import token_required

parking_bp = Blueprint('parking', __name__)


@parking_bp.route('', methods=['GET'])
@token_required
def get_parking_entries(current_user):
    """Get parking entries."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = ParkingEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(ParkingEntry.vehicle_id == vehicle_id)
    
    entries = query.order_by(ParkingEntry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'entries': [e.to_dict() for e in entries.items],
        'total': entries.total,
        'pages': entries.pages,
        'current_page': page,
    })


@parking_bp.route('', methods=['POST'])
@token_required
def create_parking_entry(current_user):
    """Create a new parking entry."""
    data = request.get_json()
    
    vehicle = Vehicle.query.filter_by(
        id=data.get('vehicle_id'),
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    # Parse date - support both 'date' and 'entry_date' field names
    entry_date = datetime.utcnow().date()
    if data.get('date'):
        entry_date = datetime.fromisoformat(data['date'].replace('Z', '+00:00')).date()
    elif data.get('entry_date'):
        entry_date = datetime.fromisoformat(data['entry_date'].replace('Z', '+00:00')).date()
    
    # Parse start/end times
    start_datetime = None
    end_datetime = None
    if data.get('start_time'):
        start_datetime = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
    if data.get('end_time'):
        end_datetime = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
    
    # Parse permit expiry
    permit_expires = None
    if data.get('permit_valid_until'):
        permit_expires = datetime.fromisoformat(data['permit_valid_until'].replace('Z', '+00:00')).date()
    elif data.get('permit_expires'):
        permit_expires = datetime.fromisoformat(data['permit_expires'].replace('Z', '+00:00')).date()
    
    # Parse next due date for recurring
    next_due_date = None
    is_recurring = data.get('recurring', False)
    recurrence_type = data.get('recurrence_type')
    
    if data.get('next_due_date'):
        next_due_date = datetime.fromisoformat(data['next_due_date'].replace('Z', '+00:00')).date()
    elif is_recurring and permit_expires:
        # Auto-calculate next due date based on recurrence type
        from dateutil.relativedelta import relativedelta
        if recurrence_type == 'daily':
            next_due_date = permit_expires + relativedelta(days=1)
        elif recurrence_type == 'weekly':
            next_due_date = permit_expires + relativedelta(weeks=1)
        elif recurrence_type == 'monthly':
            next_due_date = permit_expires + relativedelta(months=1)
        else:  # annual
            next_due_date = permit_expires + relativedelta(years=1)
    
    entry = ParkingEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        amount=data.get('total_cost') or data.get('cost') or data.get('amount', 0),
        title=data.get('location_name') or data.get('location'),
        description=data.get('notes'),
        parking_type=data.get('parking_type', 'hourly'),
        location=data.get('location_name') or data.get('location'),
        location_address=data.get('location_address'),
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        duration_minutes=data.get('duration_minutes'),
        recurring=is_recurring,
        recurrence_type=recurrence_type,
        next_due_date=next_due_date,
        reminder_days=data.get('reminder_days', 7),
        permit_number=data.get('permit_number'),
        permit_expires=permit_expires,
        notes=data.get('notes'),
    )
    
    db.session.add(entry)
    db.session.commit()
    
    return jsonify({
        'message': 'Parking entry created',
        'entry': entry.to_dict()
    }), 201


@parking_bp.route('/<int:entry_id>', methods=['GET'])
@token_required
def get_parking_entry(current_user, entry_id):
    """Get a specific parking entry."""
    entry = ParkingEntry.query.join(Vehicle).filter(
        ParkingEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    return jsonify(entry.to_dict())


@parking_bp.route('/<int:entry_id>', methods=['PUT'])
@token_required
def update_parking_entry(current_user, entry_id):
    """Update a parking entry."""
    entry = ParkingEntry.query.join(Vehicle).filter(
        ParkingEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    data = request.get_json()
    
    allowed = ['entry_date', 'cost', 'location_name', 'location_address',
               'latitude', 'longitude', 'parking_type', 'start_time', 'end_time',
               'duration_minutes', 'is_permit', 'permit_number',
               'permit_valid_until', 'payment_method', 'notes']
    
    for field in allowed:
        if field in data:
            if field in ['entry_date', 'start_time', 'end_time'] and data[field]:
                setattr(entry, field, datetime.fromisoformat(data[field]))
            elif field == 'permit_valid_until' and data[field]:
                setattr(entry, field, datetime.fromisoformat(data[field]).date())
            else:
                setattr(entry, field, data[field])
    
    db.session.commit()
    
    return jsonify({
        'message': 'Parking entry updated',
        'entry': entry.to_dict()
    })


@parking_bp.route('/<int:entry_id>', methods=['DELETE'])
@token_required
def delete_parking_entry(current_user, entry_id):
    """Delete a parking entry."""
    entry = ParkingEntry.query.join(Vehicle).filter(
        ParkingEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    db.session.delete(entry)
    db.session.commit()
    
    return jsonify({'message': 'Parking entry deleted'})


@parking_bp.route('/permits', methods=['GET'])
@token_required
def get_active_permits(current_user):
    """Get active parking permits."""
    from datetime import date
    
    entries = ParkingEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id,
        ParkingEntry.is_permit == True,
        (ParkingEntry.permit_valid_until.is_(None)) | 
        (ParkingEntry.permit_valid_until >= date.today())
    ).order_by(ParkingEntry.permit_valid_until.asc()).all()
    
    return jsonify({
        'permits': [e.to_dict() for e in entries]
    })


@parking_bp.route('/stats', methods=['GET'])
@token_required
def get_parking_stats(current_user):
    """Get parking statistics."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    query = ParkingEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(ParkingEntry.vehicle_id == vehicle_id)
    
    entries = query.all()
    
    total_cost = sum(e.cost or 0 for e in entries)
    total_duration = sum(e.duration_minutes or 0 for e in entries)
    
    # By type
    by_type = {}
    for entry in entries:
        ptype = entry.parking_type or 'other'
        if ptype not in by_type:
            by_type[ptype] = {'count': 0, 'cost': 0, 'duration': 0}
        by_type[ptype]['count'] += 1
        by_type[ptype]['cost'] += float(entry.cost or 0)
        by_type[ptype]['duration'] += entry.duration_minutes or 0
    
    # Top locations
    locations = {}
    for entry in entries:
        loc = entry.location_name or 'Unknown'
        if loc not in locations:
            locations[loc] = {'count': 0, 'cost': 0}
        locations[loc]['count'] += 1
        locations[loc]['cost'] += float(entry.cost or 0)
    
    top_locations = sorted(
        locations.items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )[:5]
    
    return jsonify({
        'total_cost': float(total_cost),
        'total_duration_minutes': total_duration,
        'entry_count': len(entries),
        'by_type': by_type,
        'top_locations': dict(top_locations),
    })
