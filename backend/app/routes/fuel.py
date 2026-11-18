"""
GearCargo - Fuel Entry Routes
"""

from app.services.mutations import mutation_endpoint, commit_mutation

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app import db
from app.models import Vehicle, FuelEntry, Entry
from app.routes.auth import token_required
from app.utils.entryparse import (
    REQUIRED_FIELD_KEY,
    InvalidFieldError,
    invalid_field_response,
    parse_amount,
    parse_currency_code,
    parse_iso_date,
    parse_optional_amount,
    parse_optional_int,
)
from app.services.currency import sum_to_display, get_rates_cached
from app.services.fuel_efficiency import measurement_statuses, measurement_warnings, recalculate_efficiencies
from app.utils.timeutils import utc_today

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


def _entry_payload(entry, measurement_status):
    return {**entry.to_dict(), 'measurement_status': measurement_status}


def _saved_entry_response(message, entry, measurements):
    """The saved fill, why it has or lacks a figure, and non-blocking warnings."""
    measurement = measurements.get(entry.id)
    return {
        'message': message,
        'entry': _entry_payload(entry, measurement.status if measurement else None),
        'warnings': measurement_warnings(measurement),
    }


@fuel_bp.route('', methods=['GET'])
@token_required
def get_fuel_entries(current_user):
    """Get fuel entries for user's vehicles."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = max(1, min(request.args.get('per_page', 20, type=int), 100))
    
    query = FuelEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    )
    
    if vehicle_id:
        query = query.filter(FuelEntry.vehicle_id == vehicle_id)
    
    # FuelEntry inherits date from Entry
    # R4-15: batch the attachments the rows serialize — one query for the
    # page instead of one per entry.
    entries = query.options(selectinload(FuelEntry.attachments)) \
        .order_by(FuelEntry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    statuses = measurement_statuses(current_user.id, list({entry.vehicle_id for entry in entries.items}))

    return jsonify({
        'entries': [_entry_payload(entry, statuses.get(entry.id)) for entry in entries.items],
        'total': entries.total,
        'pages': entries.pages,
        'current_page': page,
    })


@fuel_bp.route('', methods=['POST'])
@token_required
@mutation_endpoint(FuelEntry)
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
    if data.get('liters', data.get('volume')) in (None, ''):
        return jsonify({'error': 'Fuel amount (liters) is required',
                        'message_key': REQUIRED_FIELD_KEY}), 400

    # Every parse below raises InvalidFieldError, caught once — malformed input
    # used to escape as a 500 (R4-10) or reach a Numeric/Integer column raw
    # (R4-11). Both spellings of each field are supported, as before: the alias
    # chain picks the value, the parser validates whichever one it picked.
    try:
        liters = parse_amount(data.get('liters', data.get('volume')),
                              'Fuel amount must be a number')
        price_per_liter = parse_optional_amount(
            data.get('price_per_liter', data.get('price_per_unit')),
            'Price per litre must be a number')
        total_price = parse_optional_amount(
            data.get('total_price', data.get('total_cost')),
            'Total price must be a number')
        if total_price is None and liters and price_per_liter:
            total_price = liters * price_per_liter

        odometer = parse_optional_int(data.get('odometer', data.get('mileage')),
                                      'Odometer must be a number')
        currency = parse_currency_code(data.get('currency') or current_user.chosen_currency)

        entry_date = utc_today()
        if data.get('date'):
            entry_date = parse_iso_date(data['date'])
        elif data.get('entry_date'):
            entry_date = parse_iso_date(data['entry_date'])
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status
    
    entry = FuelEntry(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        date=entry_date,
        odometer=odometer,
        amount=total_price,
        currency=currency,
        liters=liters,
        price_per_liter=price_per_liter,
        total_price=total_price,
        fuel_type=data.get('fuel_type', vehicle.fuel_type),
        full_tank=data.get('full_tank', data.get('is_full_tank', True)),
        station=data.get('station') or data.get('station_name'),
        station_address=data.get('station_address') or data.get('station_location'),
        notes=data.get('notes'),
    )
    
    # Update vehicle mileage if provided
    if entry.odometer and entry.odometer > (vehicle.current_mileage or 0):
        vehicle.current_mileage = entry.odometer

    db.session.add(entry)
    db.session.flush()
    # Recompute only this fill's full-to-full window. Existing stale history
    # is repaired explicitly with rebuild-unit-metrics, outside HTTP requests.
    measurements = recalculate_efficiencies(vehicle.id, current_user.id, positions=[(entry.date, entry.id)])
    commit_mutation()

    # Auto-sync to calendar if enabled
    if current_user.calendar_enabled:
        try:
            from app.services.calendar_service import sync_entry_to_calendar
            sync_entry_to_calendar(current_user, 'fuel', entry, 'create')
        except Exception as e:
            current_app.logger.warning(f"Calendar sync failed for fuel: {e}")

    return jsonify(_saved_entry_response('Fuel entry created', entry, measurements)), 201


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

    statuses = measurement_statuses(current_user.id, [entry.vehicle_id])
    return jsonify(_entry_payload(entry, statuses.get(entry.id)))


@fuel_bp.route('/<int:entry_id>', methods=['PUT'])
@token_required
@mutation_endpoint(FuelEntry, 'entry_id')
def update_fuel_entry(current_user, entry_id):
    """Update a fuel entry."""
    entry = FuelEntry.query.join(Vehicle).filter(
        FuelEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    data = request.get_json()
    
    # Parsed up front so a rejected field cannot leave the earlier ones already
    # applied — this handler used to assign field by field as it went, and the
    # mileage/efficiency recalculation below then made the half-write durable
    # (R4-11).
    try:
        parsed_columns = {}
        if 'date' in data or 'entry_date' in data:
            parsed_columns['date'] = parse_iso_date(
                data.get('date') or data.get('entry_date'))
        if 'odometer' in data or 'mileage' in data:
            parsed_columns['odometer'] = parse_optional_int(
                data.get('odometer', data.get('mileage')),
                'Odometer must be a number')
        if 'liters' in data or 'volume' in data:
            parsed_columns['liters'] = parse_optional_amount(
                data.get('liters', data.get('volume')),
                'Fuel amount must be a number')
        if 'price_per_liter' in data or 'price_per_unit' in data:
            parsed_columns['price_per_liter'] = parse_optional_amount(
                data.get('price_per_liter', data.get('price_per_unit')),
                'Price per litre must be a number')
        if 'total_price' in data or 'total_cost' in data:
            total_price = parse_optional_amount(
                data.get('total_price', data.get('total_cost')),
                'Total price must be a number')
            parsed_columns['total_price'] = total_price
            parsed_columns['amount'] = total_price
        # F48 — allow editing the per-entry currency (ignore blank so it never
        # clears an existing value). The column is String(3), so the code is
        # length-checked here rather than trusted from the client.
        if data.get('currency'):
            parsed_columns['currency'] = parse_currency_code(data['currency'])
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    previous_position = (entry.date, entry.id)
    for column, value in parsed_columns.items():
        setattr(entry, column, value)

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
    # A date move affects its old and new windows, including same-day ID order.
    measurements = recalculate_efficiencies(entry.vehicle_id, current_user.id,
                                            positions=[previous_position, (entry.date, entry.id)])

    commit_mutation()

    return jsonify(_saved_entry_response('Fuel entry updated', entry, measurements))


@fuel_bp.route('/<int:entry_id>', methods=['DELETE'])
@token_required
@mutation_endpoint(FuelEntry, 'entry_id')
def delete_fuel_entry(current_user, entry_id):
    """Delete a fuel entry."""
    entry = FuelEntry.query.join(Vehicle).filter(
        FuelEntry.id == entry_id,
        Vehicle.user_id == current_user.id
    ).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    vehicle_id = entry.vehicle_id
    previous_position = (entry.date, entry.id)
    db.session.delete(entry)
    db.session.flush()
    _recalculate_vehicle_current_mileage(current_user.id, vehicle_id)
    recalculate_efficiencies(vehicle_id, current_user.id, positions=[previous_position])
    commit_mutation()
    
    return jsonify({'message': 'Fuel entry deleted'})


@fuel_bp.route('/stations', methods=['GET'])
@token_required
def get_fuel_stations(current_user):
    """Per-station price insights from the user's own fill history (F26).

    One grouped query (top 15 stations by visit count) + a bounded loop for
    each station's last paid price. When a vehicle_id is given, its fuel type
    is compared against the current national average (cached by the fuel-price
    service); delta_vs_national_pct is omitted when no live price is available
    (baseline fallback data is never used as a comparison basis).
    """
    vehicle_id = request.args.get('vehicle_id', type=int)

    def _scope(q):
        q = q.join(Vehicle, FuelEntry.vehicle_id == Vehicle.id).filter(
            Vehicle.user_id == current_user.id,
            FuelEntry.station.isnot(None),
            FuelEntry.station != '',
            FuelEntry.price_per_liter.isnot(None),
        )
        if vehicle_id:
            q = q.filter(FuelEntry.vehicle_id == vehicle_id)
        return q

    rows = (
        _scope(db.session.query(
            FuelEntry.station,
            func.count(FuelEntry.id),
            func.avg(FuelEntry.price_per_liter),
            func.max(FuelEntry.date),
        ))
        .group_by(FuelEntry.station)
        .order_by(func.count(FuelEntry.id).desc())
        .limit(15)
        .all()
    )

    # National price for the vehicle's fuel type — per-vehicle only (the
    # "all vehicles" view has no single fuel type to compare against).
    national_price = None
    currency_code = None
    if vehicle_id and rows:
        vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=current_user.id).first()
        fuel_key = {
            'petrol': 'petrol', 'regular': 'petrol', 'premium': 'premium',
            'diesel': 'diesel', 'lpg': 'lpg', 'hybrid': 'petrol',
        }.get((vehicle.fuel_type or '').lower()) if vehicle else None
        if fuel_key:
            try:
                from app.services.fuel_price_service import get_prices
                country = (current_user.country_preference or 'UK').upper()
                prices = get_prices(country, current_app._get_current_object())
                if prices and not prices.get('baseline') and prices.get(fuel_key) is not None:
                    national_price = float(prices[fuel_key])
                    currency_code = prices.get('currency_code')
            except Exception as e:
                current_app.logger.debug(f'fuel stations: national price unavailable: {e}')

    stations = []
    for name, fills, avg_price, _last_date in rows:
        last = (
            _scope(FuelEntry.query)
            .filter(FuelEntry.station == name)
            .order_by(FuelEntry.date.desc(), FuelEntry.id.desc())
            .first()
        )
        avg_val = round(float(avg_price), 3) if avg_price is not None else None
        item = {
            'name': name,
            'fills': int(fills),
            'avg_price': avg_val,
            'last_price': float(last.price_per_liter) if last and last.price_per_liter else None,
            'last_date': last.date.isoformat() if last and last.date else None,
        }
        if national_price and avg_val:
            item['delta_vs_national_pct'] = round(
                (avg_val - national_price) / national_price * 100, 1)
        stations.append(item)

    return jsonify({
        'stations': stations,
        'national_price': national_price,
        'currency_code': currency_code,
    })


@fuel_bp.route('/stats', methods=['GET'])
@token_required
def get_fuel_stats(current_user):
    """Get fuel statistics."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    # M9: aggregate in the DB (grouped SQL) instead of loading the vehicle's
    # entire fuel history into worker memory. Same F28 currency handling — the
    # per-currency cost sums are just sourced from SQL now.
    filters = [Vehicle.user_id == current_user.id]
    if vehicle_id:
        filters.append(FuelEntry.vehicle_id == vehicle_id)

    display_ccy = (getattr(current_user, 'currency', None) or 'GBP').upper()

    # Count + litre total in one row (no FX involved for volume).
    entry_count, total_liters = (
        db.session.query(
            func.count(FuelEntry.id),
            func.coalesce(func.sum(FuelEntry.liters), 0),
        )
        .join(Vehicle).filter(*filters)
        .one()
    )

    if not entry_count:
        return jsonify({
            'total_cost': 0,
            'total_liters': 0,
            'entry_count': 0,
            'avg_efficiency': None,
            'efficiency_unit': 'L/100km',
            'volume_unit': 'liters',
            'avg_price_per_liter': None,
            'display_currency': display_ccy,
            'converted': True,
            'fx_applied': False,
        })

    # F28 — per-currency cost sums grouped in SQL, then converted into the
    # display currency before adding. Re-fold by upper-cased currency exactly as
    # the old row loop did (so 'eur'/'EUR' merge into one bucket).
    ccy_rows = (
        db.session.query(
            FuelEntry.currency,
            func.coalesce(func.sum(FuelEntry.total_price), 0),
        )
        .join(Vehicle).filter(*filters)
        .group_by(FuelEntry.currency)
        .all()
    )
    per_ccy = {}
    for ccy, amt in ccy_rows:
        k = ccy.upper() if ccy else None
        per_ccy[k] = per_ccy.get(k, 0.0) + float(amt or 0)
    rates = get_rates_cached(current_app._get_current_object())
    total_cost, converted, fx_applied = sum_to_display(
        list(per_ccy.items()), display_ccy, rates)

    # Consumption weights measured windows by canonical kilometres; unit prices
    # retain their existing arithmetic-average contract.
    from app.services.fuel_efficiency import weighted_efficiency_query
    avg_eff = weighted_efficiency_query(*filters)
    avg_ppl = (
        db.session.query(func.avg(FuelEntry.price_per_liter))
        .join(Vehicle)
        .filter(*filters, FuelEntry.price_per_liter.isnot(None), FuelEntry.price_per_liter != 0)
        .scalar()
    )

    return jsonify({
        'total_cost': total_cost,
        'total_liters': float(total_liters or 0),
        'entry_count': entry_count,
        'avg_efficiency': float(avg_eff) if avg_eff is not None else None,
        'efficiency_unit': 'L/100km',
        'volume_unit': 'liters',
        'avg_price_per_liter': float(avg_ppl) if avg_ppl is not None else None,
        'display_currency': display_ccy,
        'converted': converted,      # False → an amount had no currency or no usable FX rate
        'fx_applied': fx_applied,    # True → amounts crossed currencies
    })


@fuel_bp.route('/recent', methods=['GET'])
@token_required
def get_recent_fuel(current_user):
    """Get recent fuel entries."""
    limit = request.args.get('limit', 5, type=int)
    
    entries = FuelEntry.query.join(Vehicle).filter(
        Vehicle.user_id == current_user.id
    ).options(selectinload(FuelEntry.attachments)) \
        .order_by(FuelEntry.date.desc()).limit(limit).all()
    
    return jsonify({
        'entries': [e.to_dict() for e in entries]
    })
