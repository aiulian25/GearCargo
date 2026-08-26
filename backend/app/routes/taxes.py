"""
GearCargo - Tax Entry Routes
"""

from datetime import datetime, date, timezone
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func, extract

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
    per_page = max(1, min(request.args.get('per_page', 20, type=int), 100))
    
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
    entry_date = datetime.now(timezone.utc).date()
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
        currency=data.get('currency') or current_user.currency or 'EUR',
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

    # F41 — request keys mapped to the REAL TaxEntry columns (same alias-map
    # idiom F18 applied to services/repairs). The previous allowed-list wrote
    # phantom names (valid_from, cost, entry_date, payment_method, filed_online)
    # that setattr silently discarded on commit — editing a tax's date/amount/
    # valid-until persisted nothing. Aliases first, canonical names last so the
    # canonical value wins when both are sent.
    field_aliases = {
        'entry_date': 'date', 'date': 'date',
        'cost': 'amount', 'amount': 'amount',
        'currency': 'currency',
        'tax_type': 'tax_type', 'tax_year': 'tax_year', 'tax_period': 'tax_period',
        'description': 'description',
        'valid_until': 'due_date', 'due_date': 'due_date',
        'paid_date': 'paid_date', 'filing_date': 'filing_date',
        'next_due_date': 'next_due_date',
        'reference_number': 'reference_number',
        'status': 'status',
        'recurring': 'recurring', 'recurrence_type': 'recurrence_type',
        'reminder_days': 'reminder_days',
        'notes': 'notes',
    }
    # entries.date is NOT NULL — never clear it; the other dates are nullable.
    date_columns = {'date', 'due_date', 'paid_date', 'filing_date', 'next_due_date'}

    for key, column in field_aliases.items():
        if key not in data:
            continue
        value = data[key]
        if column in date_columns:
            if value:
                setattr(entry, column,
                        datetime.fromisoformat(str(value).replace('Z', '+00:00')).date())
            elif column != 'date':
                setattr(entry, column, None)
        elif column == 'amount':
            if value is not None:
                entry.amount = float(value)
        else:
            setattr(entry, column, value)

    # insurance_policy_id — ownership-validated (kept from the original handler).
    if 'insurance_policy_id' in data:
        if data['insurance_policy_id']:
            policy = InsurancePolicy.query.filter_by(
                id=data['insurance_policy_id'],
                user_id=current_user.id,
                vehicle_id=entry.vehicle_id,
            ).first()
            if policy:
                entry.insurance_policy_id = policy.id
        else:
            entry.insurance_policy_id = None

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
        TaxEntry.due_date.isnot(None),
        TaxEntry.due_date <= cutoff,
        TaxEntry.due_date >= date.today()
    ).order_by(TaxEntry.due_date.asc()).all()
    
    return jsonify({
        'entries': [e.to_dict() for e in entries]
    })


@taxes_bp.route('/stats', methods=['GET'])
@token_required
def get_tax_stats(current_user):
    """Get tax statistics."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    # M9: DB aggregation instead of loading every tax row into memory.
    filters = [Vehicle.user_id == current_user.id]
    if vehicle_id:
        filters.append(TaxEntry.vehicle_id == vehicle_id)

    entry_count, total_cost = (
        db.session.query(
            func.count(TaxEntry.id),
            func.coalesce(func.sum(TaxEntry.amount), 0),
        )
        .join(Vehicle).filter(*filters)
        .one()
    )

    # By type — grouped; NULL/'' → 'other' (COALESCE only catches NULL).
    by_type = {}
    for ttype_raw, cnt, cost in (
        db.session.query(
            TaxEntry.tax_type,
            func.count(TaxEntry.id),
            func.coalesce(func.sum(TaxEntry.amount), 0),
        )
        .join(Vehicle).filter(*filters)
        .group_by(TaxEntry.tax_type)
        .all()
    ):
        ttype = ttype_raw or 'other'
        if ttype not in by_type:
            by_type[ttype] = {'count': 0, 'cost': 0}
        by_type[ttype]['count'] += cnt
        by_type[ttype]['cost'] += float(cost or 0)

    # Yearly breakdown — group by the calendar year of `date` in SQL.
    # extract() is portable (SQLite → CAST(STRFTIME…), Postgres → EXTRACT); the
    # year comes back int/Decimal, so int() it to match the old `date.year` key.
    yearly = {}
    for year, cost in (
        db.session.query(
            extract('year', TaxEntry.date),
            func.coalesce(func.sum(TaxEntry.amount), 0),
        )
        .join(Vehicle).filter(*filters)
        .group_by(extract('year', TaxEntry.date))
        .all()
    ):
        yearly[int(year)] = float(cost or 0)

    return jsonify({
        'total_cost': float(total_cost or 0),
        'entry_count': entry_count,
        'by_type': by_type,
        'yearly_breakdown': yearly,
    })
