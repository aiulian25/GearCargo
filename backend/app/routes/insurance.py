"""
GearCargo - Insurance Routes
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify, current_app

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
    per_page = request.args.get('per_page', 20, type=int)
    
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
    policies = InsurancePolicy.query.filter_by(user_id=current_user.id).all()
    
    active = [p for p in policies if p.is_active]
    total_premium = sum(p.premium or 0 for p in active)
    
    # By type
    by_type = {}
    for p in policies:
        ptype = p.policy_type or 'other'
        if ptype not in by_type:
            by_type[ptype] = {'count': 0, 'active': 0, 'premium': 0}
        by_type[ptype]['count'] += 1
        if p.is_active:
            by_type[ptype]['active'] += 1
            by_type[ptype]['premium'] += float(p.premium or 0)
    
    # By provider
    by_provider = {}
    for p in policies:
        provider = p.provider
        if provider not in by_provider:
            by_provider[provider] = {'count': 0, 'active': 0}
        by_provider[provider]['count'] += 1
        if p.is_active:
            by_provider[provider]['active'] += 1
    
    # Expiring soon
    expiring_soon = sum(1 for p in active if p.is_expiring_soon)
    
    return jsonify({
        'total_policies': len(policies),
        'active_policies': len(active),
        'total_active_premium': float(total_premium),
        'expiring_soon': expiring_soon,
        'by_type': by_type,
        'by_provider': by_provider,
    })
