"""
GearCargo - Repair Entry Routes
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

from app import db
from app.models import Vehicle, RepairEntry
from app.routes.auth import token_required

repairs_bp = Blueprint('repairs', __name__)


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
    
    if not data.get('repair_type'):
        return jsonify({'error': 'Repair type is required'}), 400
    
    # Parse date - support both 'date' and 'entry_date' field names
    entry_date = datetime.utcnow().date()
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
        title=data.get('repair_type'),
        description=data.get('description'),
        repair_type=data['repair_type'],
        diagnosis=data.get('diagnosis'),
        symptoms=data.get('symptoms'),
        provider=data.get('shop_name') or data.get('provider_name') or data.get('provider'),
        garage_name=data.get('shop_name') or data.get('garage_name') or data.get('provider_name'),
        garage_address=data.get('provider_location') or data.get('garage_address'),
        labor_cost=data.get('labor_cost'),
        parts_cost=data.get('parts_cost'),
        parts_replaced=data.get('parts_replaced'),
        severity=data.get('severity', 'medium'),
        under_warranty=data.get('warranty_covered') or data.get('under_warranty', False),
        notes=data.get('notes'),
    )
    
    if entry.odometer and entry.odometer > vehicle.current_mileage:
        vehicle.current_mileage = entry.odometer
    
    db.session.add(entry)
    db.session.commit()
    
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
    
    allowed = ['entry_date', 'mileage', 'cost', 'repair_type', 'description',
               'diagnosis', 'parts_replaced', 'labor_cost', 'parts_cost',
               'provider_name', 'provider_location', 'provider_phone',
               'severity', 'is_recurring', 'warranty_covered',
               'insurance_covered', 'insurance_claim_number', 'notes']
    
    for field in allowed:
        if field in data:
            if field == 'entry_date' and data[field]:
                setattr(entry, field, datetime.fromisoformat(data[field]))
            else:
                setattr(entry, field, data[field])
    
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
    
    query = RepairEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(RepairEntry.vehicle_id == vehicle_id)
    
    entries = query.all()
    
    total_cost = sum(e.cost or 0 for e in entries)
    warranty_savings = sum(e.cost or 0 for e in entries if e.warranty_covered)
    insurance_claims = sum(e.cost or 0 for e in entries if e.insurance_covered)
    
    # By severity
    by_severity = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
    for entry in entries:
        severity = entry.severity or 'medium'
        if severity in by_severity:
            by_severity[severity] += 1
    
    # By type
    by_type = {}
    for entry in entries:
        rtype = entry.repair_type or 'other'
        if rtype not in by_type:
            by_type[rtype] = {'count': 0, 'cost': 0}
        by_type[rtype]['count'] += 1
        by_type[rtype]['cost'] += float(entry.cost or 0)
    
    return jsonify({
        'total_cost': float(total_cost),
        'entry_count': len(entries),
        'warranty_savings': float(warranty_savings),
        'insurance_claims': float(insurance_claims),
        'by_severity': by_severity,
        'by_type': by_type,
    })
