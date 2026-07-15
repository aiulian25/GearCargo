"""
GearCargo - Widget API Routes (Gethomepage integration)
"""

import hashlib
import secrets
from datetime import date
from functools import wraps

from flask import Blueprint, request, jsonify

from app import db
from app.models import User, Vehicle, Reminder
from app.models.service import ServiceEntry
from app.models.repair import RepairEntry
from app.models.fuel import FuelEntry
from app.routes.auth import token_required

widget_bp = Blueprint('widget', __name__)


def _hash_api_key(raw_key: str) -> str:
    """Return the SHA-256 hex digest of a raw API key (S07)."""
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()


def api_key_required(f):
    """Decorator to require valid API key via X-API-Key header or query param."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('key')

        if not api_key:
            return jsonify({'error': 'API key is required'}), 401

        # S07: look up by SHA-256 hash, never by plaintext
        hashed = _hash_api_key(api_key)
        user = User.query.filter(
            User.api_key_hash == hashed,
            User.is_active == True
        ).first()
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
              - field: due_soon
                label: Due (14d)
              - field: next_due
                label: Next Due
              - field: fines_owed
                label: Fines Owed
              - field: fuel_price
                label: Fuel Price

    F38 fields: `due_soon` counts unified due items (reminders, service
    next-due, tax/insurance/document expiry, permits, consumable wear, fines)
    in the next 14 days; `next_due` describes the most urgent one;
    `fines_owed` sums outstanding parking fines; `fuel_price` is this week's
    national DIESEL price for the user's preferred country (one line is all
    Gethomepage shows — diesel chosen as the documented default). Each field
    degrades independently ('None'/'N/A') — the widget never 500s a homepage.
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

    # --- F38: actionable signals. Each block is independently guarded so a
    #     failure degrades to 'None'/'N/A' — the widget must never 500 a
    #     homelab homepage.

    # Unified due items in the next 14 days (F4 feed).
    due_soon = 0
    next_due = 'None'
    try:
        from app.services.due import build_due_items
        items = build_due_items(current_user.id, days=14)
        due_soon = len(items)
        if items:
            top = items[0]
            label = (top.get('title') or '')[:40]
            if top.get('vehicle_name'):
                label += f" — {top['vehicle_name']}"
            if top.get('days_left') is not None:
                label += f" ({top['days_left']}d)"
            next_due = label
    except Exception:
        pass

    # Outstanding parking fines (same filter as GET /parking/fines, F14).
    fines_owed = 'N/A'
    try:
        from app.models import ParkingEntry
        fine_rows = ParkingEntry.query.join(Vehicle).filter(
            Vehicle.user_id == current_user.id,
            ParkingEntry.parking_type == 'fine',
            db.or_(
                ParkingEntry.fine_status.in_(('pending', 'contested')),
                ParkingEntry.fine_status.is_(None),
            ),
        ).all()
        total_owed = sum(float(r.amount or 0) for r in fine_rows)
        fines_owed = f"{total_owed:.2f} {getattr(current_user, 'currency', 'GBP') or 'GBP'}"
    except Exception:
        pass

    # This week's national diesel price for the user's preferred country
    # (Redis-cached weekly data; baseline fallback keeps this populated).
    fuel_price = 'N/A'
    try:
        from flask import current_app
        from app.services.fuel_price_service import get_prices
        country = (current_user.country_preference or 'UK').upper()
        prices = get_prices(country, current_app._get_current_object())
        if prices and prices.get('diesel') is not None:
            fuel_price = f"diesel {prices['diesel']} {prices.get('currency', '')}/L"
    except Exception:
        pass

    return jsonify({
        'vehicles': vehicle_count,
        'service_records': service_count + repair_count,
        'reminders': reminder_count,
        'next_reminder': next_reminder_text,
        'subtitle': subtitle,
        # F38 — actionable fleet state.
        'due_soon': due_soon,
        'next_due': next_due,
        'fines_owed': fines_owed,
        'fuel_price': fuel_price,
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
    """Generate or regenerate an API key. Returns the raw key ONCE — never stored in DB (S07)."""
    raw_key = secrets.token_hex(32)  # 64-char hex
    current_user.api_key_hash = _hash_api_key(raw_key)
    current_user.api_key_prefix = raw_key[:8]
    current_user.api_key = None  # ensure plaintext is never/no-longer stored
    db.session.commit()

    # Raw key is returned exactly once; caller must copy it immediately
    return jsonify({
        'raw_key': raw_key,
        'prefix': current_user.api_key_prefix,
        'message': 'API key generated'
    })


@widget_bp.route('/api-key', methods=['GET'])
@token_required
def get_api_key(current_user):
    """Return whether a key exists and its display prefix — raw key is never returned after generation (S07)."""
    has_key = current_user.api_key_hash is not None
    return jsonify({
        'has_key': has_key,
        'prefix': current_user.api_key_prefix if has_key else None
    })


@widget_bp.route('/api-key', methods=['DELETE'])
@token_required
def revoke_api_key(current_user):
    """Revoke the current API key."""
    current_user.api_key_hash = None
    current_user.api_key_prefix = None
    current_user.api_key = None
    db.session.commit()

    return jsonify({'message': 'API key revoked'})
