"""
GearCargo - Insurance Routes
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func, case, and_

from app import db
from app.models import Vehicle, InsurancePolicy
from app.routes.auth import token_required

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
    
    policy = InsurancePolicy(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        policy_number=data.get('policy_number'),
        provider=data['provider'],
        policy_type=data.get('policy_type'),
        coverage_amount=data.get('coverage_amount'),
        deductible=data.get('deductible'),
        coverage_details=data.get('coverage_details'),
        premium=data.get('premium', 0),
        payment_frequency=data.get('payment_frequency'),
        currency=data.get('currency', current_user.currency),
        start_date=datetime.fromisoformat(data['start_date']).date(),
        end_date=datetime.fromisoformat(data['end_date']).date(),
        agent_name=data.get('agent_name'),
        agent_phone=data.get('agent_phone'),
        agent_email=data.get('agent_email'),
        claims_phone=data.get('claims_phone'),
        status=data.get('status', 'active'),
        auto_renew=data.get('auto_renew', False),
        notes=data.get('notes'),
    )
    
    db.session.add(policy)
    db.session.commit()
    
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
    
    for field in allowed:
        if field in data:
            if field in ['start_date', 'end_date'] and data[field]:
                setattr(policy, field, datetime.fromisoformat(data[field]).date())
            else:
                setattr(policy, field, data[field])

    # F6: editing an auto-renewed policy is the user's "confirm details" signal —
    # clear the provenance marker so the "confirm premium" prompt disappears.
    if policy.renewed_from_id is not None:
        policy.renewed_from_id = None

    db.session.commit()
    
    return jsonify({
        'message': 'Policy updated',
        'policy': policy.to_dict()
    })


@insurance_bp.route('/<int:policy_id>/cancel', methods=['POST'])
@token_required
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
    policy.end_date = date.today()
    policy.auto_renew = False
    db.session.commit()

    return jsonify({
        'message': 'Insurance policy cancelled',
        'policy': policy.to_dict()
    })


@insurance_bp.route('/<int:policy_id>', methods=['DELETE'])
@token_required
def delete_policy(current_user, policy_id):
    """Delete an insurance policy."""
    policy = InsurancePolicy.query.filter_by(
        id=policy_id,
        user_id=current_user.id
    ).first()
    
    if not policy:
        return jsonify({'error': 'Policy not found'}), 404
    
    # Unlink any tax entries that reference this policy
    try:
        from app.models import TaxEntry
        TaxEntry.query.filter_by(insurance_policy_id=policy_id).update({'insurance_policy_id': None})
    except Exception:
        pass
    
    db.session.delete(policy)
    db.session.commit()
    
    return jsonify({'message': 'Policy deleted'})


@insurance_bp.route('/active', methods=['GET'])
@token_required
def get_active_policies(current_user):
    """Get all active insurance policies."""
    policies = InsurancePolicy.query.filter(
        InsurancePolicy.user_id == current_user.id,
        InsurancePolicy.status == 'active',
        InsurancePolicy.start_date <= date.today(),
        InsurancePolicy.end_date >= date.today()
    ).order_by(InsurancePolicy.end_date.asc()).all()
    
    return jsonify({
        'policies': [p.to_dict() for p in policies]
    })


@insurance_bp.route('/expiring', methods=['GET'])
@token_required
def get_expiring_policies(current_user):
    """Get policies expiring soon."""
    days = request.args.get('days', 30, type=int)
    cutoff = date.today() + timedelta(days=days)
    
    policies = InsurancePolicy.query.filter(
        InsurancePolicy.user_id == current_user.id,
        InsurancePolicy.status == 'active',
        InsurancePolicy.end_date <= cutoff,
        InsurancePolicy.end_date >= date.today()
    ).order_by(InsurancePolicy.end_date.asc()).all()
    
    return jsonify({
        'policies': [p.to_dict() for p in policies]
    })


@insurance_bp.route('/stats', methods=['GET'])
@token_required
def get_insurance_stats(current_user):
    """Get insurance statistics."""
    # M9: DB aggregation instead of loading every policy into memory. The
    # date-based properties are translated into SQL predicates:
    #   is_active         → start_date <= today <= end_date AND status == 'active'
    #   is_expiring_soon  → 0 < (end_date - today).days <= 30
    #                       → end_date > today AND end_date <= today + 30d
    # (today / today+30 computed in Python → portable, no DB date math).
    today = date.today()
    uid = current_user.id
    active_cond = and_(
        InsurancePolicy.start_date <= today,
        InsurancePolicy.end_date >= today,
        InsurancePolicy.status == 'active',
    )
    expiring_cond = and_(
        active_cond,
        InsurancePolicy.end_date > today,
        InsurancePolicy.end_date <= today + timedelta(days=30),
    )
    active_1 = func.coalesce(func.sum(case((active_cond, 1), else_=0)), 0)
    active_premium = func.coalesce(
        func.sum(case((active_cond, func.coalesce(InsurancePolicy.premium, 0)), else_=0)), 0
    )

    total_policies, active_policies, total_premium, expiring_soon = (
        db.session.query(
            func.count(InsurancePolicy.id),
            active_1,
            active_premium,
            func.coalesce(func.sum(case((expiring_cond, 1), else_=0)), 0),
        )
        .filter(InsurancePolicy.user_id == uid)
        .one()
    )

    # By type — count ALL policies per type; active count + premium only for the
    # active ones. NULL/'' policy_type → 'other'.
    by_type = {}
    for ptype_raw, cnt, active_cnt, prem in (
        db.session.query(
            InsurancePolicy.policy_type,
            func.count(InsurancePolicy.id),
            active_1,
            active_premium,
        )
        .filter(InsurancePolicy.user_id == uid)
        .group_by(InsurancePolicy.policy_type)
        .all()
    ):
        ptype = ptype_raw or 'other'
        if ptype not in by_type:
            by_type[ptype] = {'count': 0, 'active': 0, 'premium': 0}
        by_type[ptype]['count'] += int(cnt)
        by_type[ptype]['active'] += int(active_cnt)
        by_type[ptype]['premium'] += float(prem or 0)

    # By provider — provider is NOT NULL, so it is used raw as the key.
    by_provider = {}
    for provider, cnt, active_cnt in (
        db.session.query(
            InsurancePolicy.provider,
            func.count(InsurancePolicy.id),
            active_1,
        )
        .filter(InsurancePolicy.user_id == uid)
        .group_by(InsurancePolicy.provider)
        .all()
    ):
        if provider not in by_provider:
            by_provider[provider] = {'count': 0, 'active': 0}
        by_provider[provider]['count'] += int(cnt)
        by_provider[provider]['active'] += int(active_cnt)

    return jsonify({
        'total_policies': int(total_policies),
        'active_policies': int(active_policies),
        'total_active_premium': float(total_premium or 0),
        'expiring_soon': int(expiring_soon),
        'by_type': by_type,
        'by_provider': by_provider,
    })
