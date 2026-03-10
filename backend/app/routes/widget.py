"""
GearCargo - Widget API Routes (Gethomepage integration)
"""

import secrets
from datetime import date
from functools import wraps

from flask import Blueprint, request, jsonify
from sqlalchemy import func

from app import db
from app.models import User, Vehicle, Reminder
from app.models.entry import Entry
from app.models.service import ServiceEntry
from app.models.repair import RepairEntry
from app.models.fuel import FuelEntry
from app.routes.auth import token_required

widget_bp = Blueprint('widget', __name__)


def api_key_required(f):
    """Decorator to require valid API key via X-API-Key header or query param."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('key')

        if not api_key:
            return jsonify({'error': 'API key is required'}), 401

        user = User.query.filter_by(api_key=api_key, is_active=True).first()
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401

        return f(user, *args, **kwargs)

    return decorated


@widget_bp.route('/v1/homepage', methods=['GET'])
@api_key_required
def homepage_widget(current_user):
    """
    Gethomepage widget endpoint.
    Returns vehicle stats in a format compatible with Gethomepage's customapi widget.

    Usage in Gethomepage services.yaml:
      - GearCargo:
          icon: https://your-gearcargo-url/icons/logo.png
          href: https://your-gearcargo-url
          widget:
            type: customapi
            url: https://your-gearcargo-url/api/widget/v1/homepage
            headers:
              X-API-Key: your-api-key
            mappings:
              - field: vehicles
                label: Vehicles
              - field: service_records
                label: Service Records
              - field: reminders
                label: Reminders
              - field: next_reminder
                label: Next Reminder
    """
    vehicles = Vehicle.query.filter_by(
        user_id=current_user.id,
        archived=False
    ).all()

    vehicle_count = len(vehicles)
    vehicle_ids = [v.id for v in vehicles]

    # Count service + repair records
    service_count = ServiceEntry.query.filter(
        ServiceEntry.vehicle_id.in_(vehicle_ids)
    ).count() if vehicle_ids else 0

    repair_count = RepairEntry.query.filter(
        RepairEntry.vehicle_id.in_(vehicle_ids)
    ).count() if vehicle_ids else 0

    # Active reminders
    reminder_count = Reminder.query.filter(
        Reminder.user_id == current_user.id,
        Reminder.completed == False,
        Reminder.dismissed == False
    ).count()

    # Next upcoming reminder
    next_reminder = Reminder.query.filter(
        Reminder.user_id == current_user.id,
        Reminder.completed == False,
        Reminder.dismissed == False,
        Reminder.due_date >= date.today()
    ).order_by(Reminder.due_date.asc()).first()

    next_reminder_text = 'None'
    if next_reminder:
        next_reminder_text = next_reminder.title
        if next_reminder.due_date:
            next_reminder_text += f' ({next_reminder.due_date.isoformat()})'

    # Vehicle names for subtitle
    vehicle_names = [v.name or f"{v.make} {v.model}" for v in vehicles[:3]]
    subtitle = ', '.join(vehicle_names)
    if vehicle_count > 3:
        subtitle += f' +{vehicle_count - 3} more'

    return jsonify({
        'vehicles': vehicle_count,
        'service_records': service_count + repair_count,
        'reminders': reminder_count,
        'next_reminder': next_reminder_text,
        'subtitle': subtitle,
    })


@widget_bp.route('/v1/vehicles', methods=['GET'])
@api_key_required
def homepage_vehicles(current_user):
    """Detailed per-vehicle stats for more advanced widget setups."""
    vehicles = Vehicle.query.filter_by(
        user_id=current_user.id,
        archived=False
    ).all()

    result = []
    for v in vehicles:
        service_count = ServiceEntry.query.filter_by(vehicle_id=v.id).count()
        repair_count = RepairEntry.query.filter_by(vehicle_id=v.id).count()
        fuel_count = FuelEntry.query.filter_by(vehicle_id=v.id).count()

        next_rem = Reminder.query.filter(
            Reminder.user_id == current_user.id,
            Reminder.vehicle_id == v.id,
            Reminder.completed == False,
            Reminder.dismissed == False,
            Reminder.due_date >= date.today()
        ).order_by(Reminder.due_date.asc()).first()

        result.append({
            'name': v.name or f"{v.make} {v.model}",
            'make': v.make,
            'model': v.model,
            'year': v.year,
            'license_plate': v.license_plate,
            'mileage': v.current_mileage,
            'distance_unit': v.distance_unit or 'km',
            'service_records': service_count + repair_count,
            'fuel_entries': fuel_count,
            'next_reminder': next_rem.title if next_rem else None,
            'next_reminder_date': next_rem.due_date.isoformat() if next_rem and next_rem.due_date else None,
        })

    return jsonify(result)


@widget_bp.route('/api-key', methods=['POST'])
@token_required
def generate_api_key(current_user):
    """Generate or regenerate an API key for the current user."""
    current_user.api_key = secrets.token_hex(32)
    db.session.commit()

    return jsonify({
        'api_key': current_user.api_key,
        'message': 'API key generated'
    })


@widget_bp.route('/api-key', methods=['GET'])
@token_required
def get_api_key(current_user):
    """Get the current API key."""
    return jsonify({
        'api_key': current_user.api_key
    })


@widget_bp.route('/api-key', methods=['DELETE'])
@token_required
def revoke_api_key(current_user):
    """Revoke the current API key."""
    current_user.api_key = None
    db.session.commit()

    return jsonify({'message': 'API key revoked'})
