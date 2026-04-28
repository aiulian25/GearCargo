"""
GearCargo - Tax Entry Routes
"""

from datetime import datetime, date
from flask import Blueprint, request, jsonify, current_app

from app import db
from app.models import Vehicle, TaxEntry, InsurancePolicy
from app.routes.auth import token_required

taxes_bp = Blueprint('taxes', __name__)


@taxes_bp.route('', methods=['GET'])
@token_required
def get_tax_entries(current_user):
    """Get tax entries."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = TaxEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(TaxEntry.vehicle_id == vehicle_id)
    
    entries = query.order_by(TaxEntry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'entries': [e.to_dict() for e in entries.items],
        'total': entries.total,
        'pages': entries.pages,
        'current_page': page,
    })


@taxes_bp.route('', methods=['POST'])
@token_required
def create_tax_entry(current_user):
    """Create a new tax entry."""
    data = request.get_json()
    
    vehicle = Vehicle.query.filter_by(
        id=data.get('vehicle_id'),
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    if not data.get('tax_type'):
        return jsonify({'error': 'Tax type is required'}), 400
    
    # Parse date - support both 'date' and 'entry_date' field names
    entry_date = datetime.utcnow().date()
    if data.get('date'):
        entry_date = datetime.fromisoformat(data['date'].replace('Z', '+00:00')).date()
    elif data.get('entry_date'):
        entry_date = datetime.fromisoformat(data['entry_date'].replace('Z', '+00:00')).date()
    
    # Parse due date
    due_date = None
    if data.get('valid_until'):
        due_date = datetime.fromisoformat(data['valid_until'].replace('Z', '+00:00')).date()
    elif data.get('due_date'):
        due_date = datetime.fromisoformat(data['due_date'].replace('Z', '+00:00')).date()
    
    # Parse next due date for recurring
    next_due_date = None
    if data.get('next_due_date'):
        next_due_date = datetime.fromisoformat(data['next_due_date'].replace('Z', '+00:00')).date()
    elif data.get('recurring'):
        # Auto-calculate next due date — use due_date if set, otherwise entry_date
        from dateutil.relativedelta import relativedelta
        base = due_date or entry_date
        recurrence_type = data.get('recurrence_type', 'monthly')
        if recurrence_type == 'monthly':
            step = relativedelta(months=1)
        elif recurrence_type == 'quarterly':
            step = relativedelta(months=3)
        elif recurrence_type == 'semi_annual':
            step = relativedelta(months=6)
        else:  # annual
            step = relativedelta(years=1)
        next_due_date = base + step
        # If already in the past, advance until it's in the future
        from datetime import date as date_cls
        while next_due_date <= date_cls.today():
            next_due_date = next_due_date + step
    
    # Validate insurance_policy_id if provided
    insurance_policy_id = None
    if data.get('insurance_policy_id'):
        policy = InsurancePolicy.query.filter_by(
            id=data['insurance_policy_id'],
            user_id=current_user.id,
            vehicle_id=vehicle.id
        ).first()
        if policy:
            insurance_policy_id = policy.id
    
    entry = TaxEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        amount=data.get('total_cost') or data.get('cost') or data.get('amount', 0),
        title=data.get('tax_type'),
        description=data.get('description'),
        tax_type=data['tax_type'],
        tax_year=data.get('tax_year') or entry_date.year,
        tax_period=data.get('tax_period'),
        status=data.get('status', 'paid'),
        due_date=due_date,
        paid_date=entry_date if data.get('status', 'paid') == 'paid' else None,
        reference_number=data.get('reference_number'),
        notes=data.get('notes'),
        recurring=data.get('recurring', False),
        recurrence_type=data.get('recurrence_type'),
        next_due_date=next_due_date,
        reminder_days=data.get('reminder_days', 30),
        insurance_policy_id=insurance_policy_id,
    )
    
    db.session.add(entry)
    db.session.commit()
    
    # Auto-sync to calendar if enabled
    if current_user.calendar_enabled:
        try:
            from app.services.calendar_service import sync_entry_to_calendar
            sync_entry_to_calendar(current_user, 'tax', entry, 'create')
        except Exception as e:
            current_app.logger.warning(f"Calendar sync failed for tax: {e}")
    
    return jsonify({
        'message': 'Tax entry created',
        'entry': entry.to_dict()
    }), 201


@taxes_bp.route('/<int:entry_id>', methods=['GET'])
@token_required
def get_tax_entry(current_user, entry_id):
    """Get a specific tax entry."""
    entry = TaxEntry.query.join(Vehicle).filter(
        TaxEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    return jsonify(entry.to_dict())


@taxes_bp.route('/<int:entry_id>', methods=['PUT'])
@token_required
def update_tax_entry(current_user, entry_id):
    """Update a tax entry."""
    entry = TaxEntry.query.join(Vehicle).filter(
        TaxEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    data = request.get_json()
    
    allowed = ['entry_date', 'cost', 'tax_type', 'description', 'valid_from',
               'valid_until', 'reference_number', 'payment_method', 'status',
               'filed_online', 'notes', 'recurring', 'recurrence_type', 'reminder_days',
               'insurance_policy_id', 'amount', 'date']
    
    for field in allowed:
        if field in data:
            if field == 'entry_date' and data[field]:
                setattr(entry, field, datetime.fromisoformat(data[field]))
            elif field == 'date' and data[field]:
                setattr(entry, field, datetime.fromisoformat(data[field].replace('Z', '+00:00')).date())
            elif field in ['valid_from', 'valid_until'] and data[field]:
                setattr(entry, field, datetime.fromisoformat(data[field]).date())
            elif field == 'insurance_policy_id':
                # Validate insurance policy belongs to user and vehicle
                if data[field]:
                    policy = InsurancePolicy.query.filter_by(
                        id=data[field],
                        user_id=current_user.id,
                        vehicle_id=entry.vehicle_id
                    ).first()
                    if policy:
                        setattr(entry, field, policy.id)
                else:
                    setattr(entry, field, None)
            elif field == 'amount' and data[field] is not None:
                setattr(entry, field, float(data[field]))
            else:
                setattr(entry, field, data[field])
    
    db.session.commit()
    
    return jsonify({
        'message': 'Tax entry updated',
        'entry': entry.to_dict()
    })


@taxes_bp.route('/<int:entry_id>/cancel', methods=['POST'])
@token_required
def cancel_tax_entry(current_user, entry_id):
    """Cancel a recurring tax entry, stopping future auto-generated payments."""
    entry = TaxEntry.query.join(Vehicle).filter(
        TaxEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()

    if not entry:
        return jsonify({'error': 'Entry not found'}), 404

    if not entry.recurring:
        return jsonify({'error': 'Entry is not recurring'}), 400

    entry.recurring = False
    entry.next_due_date = None
    db.session.commit()

    return jsonify({
        'message': 'Recurring tax cancelled',
        'entry': entry.to_dict()
    })


@taxes_bp.route('/<int:entry_id>', methods=['DELETE'])
@token_required
def delete_tax_entry(current_user, entry_id):
    """Delete a tax entry."""
    entry = TaxEntry.query.join(Vehicle).filter(
        TaxEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    db.session.delete(entry)
    db.session.commit()
    
    return jsonify({'message': 'Tax entry deleted'})


@taxes_bp.route('/expiring', methods=['GET'])
@token_required
def get_expiring_taxes(current_user):
    """Get taxes expiring soon."""
    days = request.args.get('days', 30, type=int)
    
    from datetime import timedelta
    cutoff = date.today() + timedelta(days=days)
    
    entries = TaxEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id,
        TaxEntry.valid_until.isnot(None),
        TaxEntry.valid_until <= cutoff,
        TaxEntry.valid_until >= date.today()
    ).order_by(TaxEntry.valid_until.asc()).all()
    
    return jsonify({
        'entries': [e.to_dict() for e in entries]
    })


@taxes_bp.route('/stats', methods=['GET'])
@token_required
def get_tax_stats(current_user):
    """Get tax statistics."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    query = TaxEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(TaxEntry.vehicle_id == vehicle_id)
    
    entries = query.all()
    
    total_cost = sum(e.cost or 0 for e in entries)
    
    # By type
    by_type = {}
    for entry in entries:
        ttype = entry.tax_type or 'other'
        if ttype not in by_type:
            by_type[ttype] = {'count': 0, 'cost': 0}
        by_type[ttype]['count'] += 1
        by_type[ttype]['cost'] += float(entry.cost or 0)
    
    # Yearly breakdown
    yearly = {}
    for entry in entries:
        year = entry.entry_date.year
        if year not in yearly:
            yearly[year] = 0
        yearly[year] += float(entry.cost or 0)
    
    return jsonify({
        'total_cost': float(total_cost),
        'entry_count': len(entries),
        'by_type': by_type,
        'yearly_breakdown': yearly,
    })
