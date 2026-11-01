"""
GearCargo - Insurance Routes
"""

from app.services.vehicle_archive import active_vehicle_condition
from app.services.mutations import mutation_endpoint, commit_mutation

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app

from app import db
from app.models import Vehicle, InsurancePolicy
from app.routes.auth import token_required
from app.utils.entryparse import (
    INVALID_DATE_KEY, InvalidFieldError, invalid_field_response, parse_amount,
    parse_currency_code, parse_iso_date, parse_optional_amount,
)
from app.utils.timeutils import utc_today

insurance_bp = Blueprint('insurance', __name__)


@insurance_bp.route('', methods=['GET'])
@token_required
def get_policies(current_user):
    """Get insurance policies."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = max(1, min(request.args.get('per_page', 20, type=int), 100))
    
    query = InsurancePolicy.query.filter_by(user_id=current_user.id)
    
    if vehicle_id:
        query = query.filter(InsurancePolicy.vehicle_id == vehicle_id)
    
    if status:
        query = query.filter(InsurancePolicy.status == status)
    
    policies = query.order_by(InsurancePolicy.end_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'policies': [p.to_dict() for p in policies.items],
        'total': policies.total,
        'pages': policies.pages,
        'current_page': page,
    })


@insurance_bp.route('', methods=['POST'])
@token_required
@mutation_endpoint(InsurancePolicy)
def create_policy(current_user):
    """Create a new insurance policy."""
    data = request.get_json()
    
    vehicle = Vehicle.query.filter_by(
        id=data.get('vehicle_id'),
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    if not data.get('provider'):
        return jsonify({'error': 'Provider is required'}), 400
    
    if not data.get('start_date') or not data.get('end_date'):
        return jsonify({'error': 'Start and end dates are required'}), 400
    
    # R4-10/R4-11: every client-supplied date, amount and code is parsed BEFORE
    # the policy is constructed, so malformed input returns the localized 400 the
    # UI renders instead of reaching the driver as a 500.
    try:
        start_date = parse_iso_date(data['start_date'])
        end_date = parse_iso_date(data['end_date'])
        premium = parse_amount(data.get('premium', 0), 'Premium must be a number')
        coverage_amount = parse_optional_amount(data.get('coverage_amount'))
        deductible = parse_optional_amount(data.get('deductible'))
        currency = parse_currency_code(data.get('currency') or current_user.currency)
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    policy = InsurancePolicy(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        policy_number=data.get('policy_number'),
        provider=data['provider'],
        policy_type=data.get('policy_type'),
        coverage_amount=coverage_amount,
        deductible=deductible,
        coverage_details=data.get('coverage_details'),
        premium=premium,
        payment_frequency=data.get('payment_frequency'),
        currency=currency,
        start_date=start_date,
        end_date=end_date,
        agent_name=data.get('agent_name'),
        agent_phone=data.get('agent_phone'),
        agent_email=data.get('agent_email'),
        claims_phone=data.get('claims_phone'),
        status=data.get('status', 'active'),
        auto_renew=data.get('auto_renew', False),
        notes=data.get('notes'),
    )
    
    db.session.add(policy)
    commit_mutation()
    
    # Auto-sync to calendar if enabled
    if current_user.calendar_enabled:
        try:
            from app.services.calendar_service import sync_entry_to_calendar
            sync_entry_to_calendar(current_user, 'insurance', policy, 'create')
        except Exception as e:
            current_app.logger.warning(f"Calendar sync failed for insurance: {e}")
    
    return jsonify({
        'message': 'Insurance policy created',
        'policy': policy.to_dict()
    }), 201


@insurance_bp.route('/<int:policy_id>', methods=['GET'])
@token_required
def get_policy(current_user, policy_id):
    """Get a specific insurance policy."""
    policy = InsurancePolicy.query.filter_by(
        id=policy_id,
        user_id=current_user.id
    ).first()
    
    if not policy:
        return jsonify({'error': 'Policy not found'}), 404
    
    return jsonify(policy.to_dict())


@insurance_bp.route('/<int:policy_id>', methods=['PUT'])
@token_required
@mutation_endpoint(InsurancePolicy, 'policy_id')
def update_policy(current_user, policy_id):
    """Update an insurance policy."""
    policy = InsurancePolicy.query.filter_by(
        id=policy_id,
        user_id=current_user.id
    ).first()
    
    if not policy:
        return jsonify({'error': 'Policy not found'}), 404
    
    data = request.get_json()
    
    allowed = ['policy_number', 'provider', 'policy_type', 'coverage_amount',
               'deductible', 'coverage_details', 'premium', 'payment_frequency',
               'currency', 'start_date', 'end_date', 'agent_name', 'agent_phone',
               'agent_email', 'claims_phone', 'status', 'auto_renew', 'notes']
    
    # Parsed into `updates` FIRST, then applied — a rejected field must never
    # leave the policy half-edited (the old loop mutated as it went).
    try:
        updates = {}
        for field in allowed:
            if field not in data:
                continue
            value = data[field]
            if field in ('start_date', 'end_date'):
                # Both columns are NOT NULL; the old `else` branch wrote '' here.
                if not value:
                    raise InvalidFieldError(INVALID_DATE_KEY,
                                            'Start and end dates are required')
                updates[field] = parse_iso_date(value)
            elif field == 'premium':
                updates[field] = parse_amount(value, 'Premium must be a number')
            elif field in ('coverage_amount', 'deductible'):
                updates[field] = parse_optional_amount(value)
            elif field == 'currency':
                updates[field] = parse_currency_code(value)
            else:
                updates[field] = value
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    for field, value in updates.items():
        setattr(policy, field, value)

    # F6: editing an auto-renewed policy is the user's "confirm details" signal —
    # clear the provenance marker so the "confirm premium" prompt disappears.
    if policy.renewed_from_id is not None:
        policy.renewed_from_id = None

    commit_mutation()
    
    return jsonify({
        'message': 'Policy updated',
        'policy': policy.to_dict()
    })


@insurance_bp.route('/<int:policy_id>/cancel', methods=['POST'])
@token_required
@mutation_endpoint(InsurancePolicy, 'policy_id')
def cancel_policy(current_user, policy_id):
    """Cancel an insurance policy, stopping future recurring costs."""
    policy = InsurancePolicy.query.filter_by(
        id=policy_id,
        user_id=current_user.id
    ).first()

    if not policy:
        return jsonify({'error': 'Policy not found'}), 404

    if policy.status == 'cancelled':
        return jsonify({'error': 'Policy is already cancelled'}), 400

    policy.status = 'cancelled'
    policy.end_date = utc_today()
    policy.auto_renew = False
    commit_mutation()

    return jsonify({
        'message': 'Insurance policy cancelled',
        'policy': policy.to_dict()
    })


@insurance_bp.route('/<int:policy_id>', methods=['DELETE'])
@token_required
@mutation_endpoint(InsurancePolicy, 'policy_id')
def delete_policy(current_user, policy_id):
    """Delete an insurance policy."""
    policy = InsurancePolicy.query.filter_by(
        id=policy_id,
        user_id=current_user.id
    ).first()
    
    if not policy:
        return jsonify({'error': 'Policy not found'}), 404
    
    # Unlink any tax entries that reference this policy
    from app.models import TaxEntry
    for entry in TaxEntry.query.filter_by(insurance_policy_id=policy_id).all():
        # ORM writes also advance the joined Entry revision.
        entry.insurance_policy_id = None
    
    db.session.delete(policy)
    commit_mutation()
    
    return jsonify({'message': 'Policy deleted'})


@insurance_bp.route('/active', methods=['GET'])
@token_required
def get_active_policies(current_user):
    """Get all active insurance policies."""
    policies = InsurancePolicy.query.filter(
        InsurancePolicy.user_id == current_user.id,
        InsurancePolicy.status == 'active',
        InsurancePolicy.start_date <= utc_today(),
        InsurancePolicy.end_date >= utc_today()
    ).order_by(InsurancePolicy.end_date.asc()).all()
    
    return jsonify({
        'policies': [p.to_dict() for p in policies]
    })


@insurance_bp.route('/expiring', methods=['GET'])
@token_required
def get_expiring_policies(current_user):
    """Get policies expiring soon."""
    days = request.args.get('days', 30, type=int)
    cutoff = utc_today() + timedelta(days=days)
    
    policies = InsurancePolicy.query.filter(
        active_vehicle_condition(InsurancePolicy),
        InsurancePolicy.user_id == current_user.id,
        InsurancePolicy.status == 'active',
        InsurancePolicy.end_date <= cutoff,
        InsurancePolicy.end_date >= utc_today()
    ).order_by(InsurancePolicy.end_date.asc()).all()
    
    return jsonify({
        'policies': [p.to_dict() for p in policies]
    })


@insurance_bp.route('/stats', methods=['GET'])
@token_required
def get_insurance_stats(current_user):
    """Counts plus separately labelled annualized and scheduled-period estimates."""
    from flask import current_app
    from app.services.currency import get_rates_cached
    from app.services.expense_ledger import load_expenses, aggregate, annualized_total, convert
    today = utc_today()
    currency = (current_user.currency or 'GBP').upper()
    rates = get_rates_cached(current_app._get_current_object())
    policies = InsurancePolicy.query.filter_by(user_id=current_user.id).all()
    active = [p for p in policies if p.status == 'active' and p.start_date <= today <= p.end_date]
    annual = annualized_total(policies, currency, rates, today)
    rows = [r for r in load_expenses(list({p.vehicle_id for p in policies}),
            today.replace(month=1, day=1), today)
            if r.category == 'insurance' and r.source.user_id == current_user.id]
    ytd = aggregate(rows, currency, rates, today.replace(month=1, day=1), today)
    by_type, by_provider = {}, {}
    for p in policies:
        kind = by_type.setdefault(p.policy_type or 'other', {'count': 0, 'active': 0, 'premium': 0.0})
        provider = by_provider.setdefault(p.provider, {'count': 0, 'active': 0})
        kind['count'] += 1
        provider['count'] += 1
        if p in active:
            kind['active'] += 1
            provider['active'] += 1
            value = convert(p.annualized_premium, p.currency, currency, rates)
            if value is not None:
                kind['premium'] = round(kind['premium'] + float(value), 2)
    return jsonify({
        'total_policies': len(policies), 'active_policies': len(active),
        'total_active_premium': annual['insurance_estimate'],
        'active_annualized_premium': annual['insurance_estimate'],
        'premium_basis': 'annualized_active_coverage',
        'scope': 'all_owned_vehicles_including_archived',
        'ytd_scheduled_estimate': ytd['insurance_estimate'],
        'period_basis': 'scheduled_insurance_estimate',
        'period_start': ytd['start_date'], 'period_end': ytd['end_date'],
        'display_currency': currency, 'currency': currency,
        'converted': annual['converted'], 'fx_applied': annual['fx_applied'],
        'unconverted': annual['unconverted'], 'ytd_converted': ytd['converted'],
        'ytd_unconverted': ytd['unconverted'],
        'expiring_soon': sum(0 < (p.end_date - today).days <= 30 for p in active),
        'by_type': by_type, 'by_provider': by_provider,
    })
