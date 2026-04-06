"""
GearCargo - Fuel Entry Routes
"""

from datetime import datetime, date
from flask import Blueprint, request, jsonify
from sqlalchemy import func

from app import db
from app.models import Vehicle, FuelEntry, Entry
from app.routes.auth import token_required

fuel_bp = Blueprint('fuel', __name__)


def _recalculate_vehicle_current_mileage(user_id, vehicle_id):
    """Set current mileage to the max recorded odometer for this vehicle."""
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=user_id).first()
    if not vehicle:
        return

    max_odometer = db.session.query(func.max(Entry.odometer)).filter(
        Entry.user_id == user_id,
        Entry.vehicle_id == vehicle_id,
        Entry.odometer.isnot(None)
    ).scalar()

    vehicle.current_mileage = max_odometer or 0


@fuel_bp.route('', methods=['GET'])
@token_required
def get_fuel_entries(current_user):
    """Get fuel entries for user's vehicles."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = FuelEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(FuelEntry.vehicle_id == vehicle_id)
    
    # FuelEntry inherits date from Entry
    entries = query.order_by(FuelEntry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'entries': [e.to_dict() for e in entries.items],
        'total': entries.total,
        'pages': entries.pages,
        'current_page': page,
    })


@fuel_bp.route('', methods=['POST'])
@token_required
def create_fuel_entry(current_user):
    """Create a new fuel entry."""
    data = request.get_json()
    
    # Validate vehicle ownership
    vehicle = Vehicle.query.filter_by(
        id=data.get('vehicle_id'),
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    # Validate required fields
    if not data.get('liters') and not data.get('volume'):
        return jsonify({'error': 'Fuel amount (liters) is required'}), 400
    
    # Support both field names for compatibility
    liters = data.get('liters') or data.get('volume')
    price_per_liter = data.get('price_per_liter') or data.get('price_per_unit')
    total_price = data.get('total_price') or data.get('total_cost')
    
    if not total_price and liters and price_per_liter:
        total_price = float(liters) * float(price_per_liter)
    
    # Parse date
    entry_date = date.today()
    if data.get('date'):
        entry_date = datetime.fromisoformat(data['date'].replace('Z', '+00:00')).date()
    elif data.get('entry_date'):
        entry_date = datetime.fromisoformat(data['entry_date'].replace('Z', '+00:00')).date()
    
    entry = FuelEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        odometer=data.get('odometer') or data.get('mileage'),
        amount=total_price,
        currency=data.get('currency', 'EUR'),
        liters=liters,
        price_per_liter=price_per_liter,
        total_price=total_price,
        fuel_type=data.get('fuel_type', vehicle.fuel_type),
        full_tank=data.get('full_tank', data.get('is_full_tank', True)),
        station=data.get('station') or data.get('station_name'),
        station_address=data.get('station_address') or data.get('station_location'),
        notes=data.get('notes'),
    )
    
    # Calculate fuel efficiency if we have odometer
    if entry.odometer:
        # Get previous fuel entry for this vehicle
        # FuelEntry inherits from Entry, so we filter directly on FuelEntry fields
        prev_entry = FuelEntry.query.filter(
            FuelEntry.vehicle_id == vehicle.id,
            FuelEntry.date < entry_date
        ).order_by(FuelEntry.date.desc()).first()
        
        if prev_entry and prev_entry.odometer:
            entry.calculate_efficiency(prev_entry.odometer)
    
    # Update vehicle mileage if provided
    if entry.odometer and entry.odometer > vehicle.current_mileage:
        vehicle.current_mileage = entry.odometer
    
    db.session.add(entry)
    db.session.commit()
    
    return jsonify({
        'message': 'Fuel entry created',
        'entry': entry.to_dict()
    }), 201


@fuel_bp.route('/<int:entry_id>', methods=['GET'])
@token_required
def get_fuel_entry(current_user, entry_id):
    """Get a specific fuel entry."""
    entry = FuelEntry.query.join(Vehicle).filter(
        FuelEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    return jsonify(entry.to_dict())


@fuel_bp.route('/<int:entry_id>', methods=['PUT'])
@token_required
def update_fuel_entry(current_user, entry_id):
    """Update a fuel entry."""
    entry = FuelEntry.query.join(Vehicle).filter(
        FuelEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    data = request.get_json()
    
    # Update fields
    if 'date' in data or 'entry_date' in data:
        date_str = data.get('date') or data.get('entry_date')
        entry.date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
    
    if 'odometer' in data or 'mileage' in data:
        entry.odometer = data.get('odometer') or data.get('mileage')
    
    if 'liters' in data or 'volume' in data:
        entry.liters = data.get('liters') or data.get('volume')
    
    if 'price_per_liter' in data or 'price_per_unit' in data:
        entry.price_per_liter = data.get('price_per_liter') or data.get('price_per_unit')
    
    if 'total_price' in data or 'total_cost' in data:
        entry.total_price = data.get('total_price') or data.get('total_cost')
        entry.amount = entry.total_price
    
    if 'fuel_type' in data:
        entry.fuel_type = data['fuel_type']
    
    if 'full_tank' in data or 'is_full_tank' in data:
        entry.full_tank = data.get('full_tank', data.get('is_full_tank'))
    
    if 'station' in data or 'station_name' in data:
        entry.station = data.get('station') or data.get('station_name')
    
    if 'station_address' in data or 'station_location' in data:
        entry.station_address = data.get('station_address') or data.get('station_location')
    
    if 'notes' in data:
        entry.notes = data['notes']

    _recalculate_vehicle_current_mileage(current_user.id, entry.vehicle_id)
    
    db.session.commit()
    
    return jsonify({
        'message': 'Fuel entry updated',
        'entry': entry.to_dict()
    })


@fuel_bp.route('/<int:entry_id>', methods=['DELETE'])
@token_required
def delete_fuel_entry(current_user, entry_id):
    """Delete a fuel entry."""
    entry = FuelEntry.query.join(Vehicle).filter(
        FuelEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    vehicle_id = entry.vehicle_id
    db.session.delete(entry)
    db.session.flush()
    _recalculate_vehicle_current_mileage(current_user.id, vehicle_id)
    db.session.commit()
    
    return jsonify({'message': 'Fuel entry deleted'})


@fuel_bp.route('/stats', methods=['GET'])
@token_required
def get_fuel_stats(current_user):
    """Get fuel statistics."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    query = FuelEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(FuelEntry.vehicle_id == vehicle_id)
    
    entries = query.all()
    
    if not entries:
        return jsonify({
            'total_cost': 0,
            'total_liters': 0,
            'entry_count': 0,
            'avg_efficiency': None,
            'avg_price_per_liter': None,
        })
    
    total_cost = sum(float(e.total_price or 0) for e in entries)
    total_liters = sum(float(e.liters or 0) for e in entries)
    efficiencies = [e.fuel_efficiency for e in entries if e.fuel_efficiency]
    prices = [float(e.price_per_liter) for e in entries if e.price_per_liter]
    
    return jsonify({
        'total_cost': total_cost,
        'total_liters': total_liters,
        'entry_count': len(entries),
        'avg_efficiency': sum(efficiencies) / len(efficiencies) if efficiencies else None,
        'avg_price_per_liter': sum(prices) / len(prices) if prices else None,
    })


@fuel_bp.route('/recent', methods=['GET'])
@token_required
def get_recent_fuel(current_user):
    """Get recent fuel entries."""
    limit = request.args.get('limit', 5, type=int)
    
    entries = FuelEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    ).order_by(FuelEntry.date.desc()).limit(limit).all()
    
    return jsonify({
        'entries': [e.to_dict() for e in entries]
    })
