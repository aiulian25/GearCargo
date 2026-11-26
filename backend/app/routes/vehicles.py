"""
GearCargo - Vehicles Routes
"""

from app.services.mutations import mutation_endpoint, commit_mutation

import os
from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Vehicle, Entry, FuelEntry, ServiceEntry, RepairEntry
from app.services import currency_review
from app.services.currency import get_rates_cached
from app.services.expense_ledger import load_expenses, aggregate, annualized_total, convert
from app.models.insurance import InsurancePolicy
from app.services.warranty import build_vehicle_warranties, warranty_summary
from app.routes.auth import token_required
from app.utils.entryparse import (
    REQUIRED_FIELD_KEY,
    InvalidFieldError,
    invalid_field_response,
    parse_optional_int,
)
from app.utils.timeutils import utc_today, isoformat_utc

vehicles_bp = Blueprint('vehicles', __name__)

CURRENCY_REVIEW_ACTIONS = {'relabel': currency_review.relabel, 'keep': currency_review.keep}


def _get_max_recorded_odometer(user_id, vehicle_id):
    """Return highest odometer recorded for a user's vehicle entries."""
    return db.session.query(func.max(Entry.odometer)).filter(
        Entry.user_id == user_id,
        Entry.vehicle_id == vehicle_id,
        Entry.odometer.isnot(None)
    ).scalar() or 0


@vehicles_bp.route('', methods=['GET'])
@token_required
def get_vehicles(current_user):
    """Get all active (non-archived) vehicles for current user."""
    vehicles = Vehicle.query.filter_by(
        user_id=current_user.id,
        archived=False
    ).order_by(Vehicle.display_order.asc(), Vehicle.created_at.desc()).all()
    
    return jsonify({
        'vehicles': [v.to_dict() for v in vehicles],
        'count': len(vehicles)
    })


@vehicles_bp.route('/archived', methods=['GET'])
@token_required
def get_archived_vehicles(current_user):
    """Get all archived vehicles for current user."""
    vehicles = Vehicle.query.filter_by(
        user_id=current_user.id,
        archived=True
    ).order_by(Vehicle.archived_at.desc()).all()
    
    return jsonify({
        'vehicles': [v.to_dict() for v in vehicles],
        'count': len(vehicles)
    })


def _archive_vehicle(vehicle):
    """Pause vehicle activity without changing its obligations or history.

    Shared by Archive and soft delete; callers commit. Scheduled jobs and due
    feeds exclude archived vehicles. Cancellation remains an explicit action.
    """
    vehicle.archived = True
    vehicle.archived_at = datetime.now(timezone.utc)


@vehicles_bp.route('/<int:vehicle_id>/archive', methods=['POST'])
@token_required
@mutation_endpoint(Vehicle, 'vehicle_id')
def archive_vehicle(current_user, vehicle_id):
    """Archive a vehicle."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()

    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404

    if vehicle.archived:
        return jsonify({'error': 'Vehicle is already archived'}), 400

    _archive_vehicle(vehicle)
    commit_mutation()

    return jsonify({
        'message': 'Vehicle archived successfully',
        'vehicle': vehicle.to_dict()
    })


@vehicles_bp.route('/<int:vehicle_id>/unarchive', methods=['POST'])
@token_required
@mutation_endpoint(Vehicle, 'vehicle_id')
def unarchive_vehicle(current_user, vehicle_id):
    """Restore an archived vehicle."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    if not vehicle.archived:
        return jsonify({'error': 'Vehicle is not archived'}), 400
    
    vehicle.archived = False
    vehicle.archived_at = None
    commit_mutation()
    
    return jsonify({
        'message': 'Vehicle restored successfully',
        'vehicle': vehicle.to_dict()
    })


@vehicles_bp.route('', methods=['POST'])
@token_required
@mutation_endpoint(Vehicle)
def create_vehicle(current_user):
    """Create a new vehicle."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('name'):
        return jsonify({'error': 'Vehicle name is required'}), 400
    
    # Check vehicle limit (only for non-admin users, or admin-created managed users with a limit)
    if current_user.vehicle_limit is not None and current_user.vehicle_limit > 0:
        current_vehicle_count = Vehicle.query.filter_by(
            user_id=current_user.id,
            archived=False
        ).count()
        if current_vehicle_count >= current_user.vehicle_limit:
            return jsonify({
                'error': 'Vehicle limit reached',
                'code': 'VEHICLE_LIMIT_REACHED',
                'limit': current_user.vehicle_limit,
                'current': current_vehicle_count
            }), 403
    
    # R2: parse before constructing — an unparseable date raised ValueError -> 500.
    try:
        purchase_date = (
            datetime.fromisoformat(data['purchase_date']).date()
            if data.get('purchase_date') else None
        )
    except (TypeError, ValueError):
        return jsonify({
            'error': 'Invalid date format',
            'message_key': 'validation.invalidDate',
        }), 400

    vehicle = Vehicle(
        user_id=current_user.id,
        name=data['name'],
        make=data.get('make') or None,
        model=data.get('model') or None,
        year=data.get('year'),
        vin=data.get('vin') or None,  # Convert empty string to None for unique constraint
        license_plate=data.get('license_plate') or None,
        color=data.get('color') or None,
        fuel_type=data.get('fuel_type', 'petrol'),
        tank_capacity=data.get('tank_capacity'),
        engine_cc=data.get('engine_cc'),
        transmission=data.get('transmission'),
        drivetrain=data.get('drivetrain'),
        current_mileage=data.get('current_mileage', 0),
        distance_unit=data.get('distance_unit', 'km'),
        # F23 — dimensions were silently discarded on create (Add form sends them).
        vehicle_height_cm=data.get('vehicle_height_cm'),
        vehicle_width_cm=data.get('vehicle_width_cm'),
        vehicle_length_cm=data.get('vehicle_length_cm'),
        vehicle_weight_kg=data.get('vehicle_weight_kg'),
        purchase_date=purchase_date,
        purchase_price=data.get('purchase_price'),
        purchase_currency=(data.get('purchase_currency') or current_user.currency or 'GBP')
            if data.get('purchase_price') is not None else data.get('purchase_currency'),
        monthly_budget=data.get('monthly_budget'),
    )
    
    db.session.add(vehicle)
    try:
        commit_mutation()
    except IntegrityError as exc:
        # R1: `vin` carries a UNIQUE constraint, so a duplicate (even another
        # user's) reached the client as an unhandled 500. Anything else is a
        # genuinely unexpected constraint failure — re-raise rather than
        # mislabel it as a VIN conflict.
        db.session.rollback()
        if 'vin' not in str(getattr(exc, 'orig', exc)).lower():
            raise
        return jsonify({
            'error': 'A vehicle with this VIN already exists',
            'message_key': 'vehicles.vinAlreadyExists',
        }), 409

    return jsonify({
        'message': 'Vehicle created successfully',
        'vehicle': vehicle.to_dict()
    }), 201


@vehicles_bp.route('/<int:vehicle_id>', methods=['GET'])
@token_required
def get_vehicle(current_user, vehicle_id):
    """Get a specific vehicle."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    from app.utils.units import distance_unit_locked
    payload = vehicle.to_dict(include_stats=True)
    payload['distance_unit_locked'] = distance_unit_locked(vehicle)
    return jsonify(payload)


@vehicles_bp.route('/<int:vehicle_id>', methods=['PUT'])
@token_required
@mutation_endpoint(Vehicle, 'vehicle_id')
def update_vehicle(current_user, vehicle_id):
    """Update a vehicle."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    data = request.get_json()
    from app.utils.units import distance_unit, distance_unit_locked
    if ('distance_unit' in data
            and distance_unit(data['distance_unit']) != distance_unit(vehicle.distance_unit)
            and distance_unit_locked(vehicle)):
        return jsonify({'error': 'Distance units cannot change while mileage, thresholds or history exist.',
                        'message_key': 'vehicles.distanceUnitLocked', 'field': 'distance_unit',
                        'code': 'DISTANCE_UNIT_LOCKED'}), 409

    # Update allowed fields — real Vehicle columns only (F21 removed the
    # phantom drive_type/body_type/notes/is_active/photo_url entries).
    allowed = ['name', 'make', 'model', 'year', 'vin', 'license_plate',
               'color', 'fuel_type', 'engine_cc', 'transmission',
               'drivetrain', 'current_mileage', 'distance_unit', 'tank_capacity',
               'vehicle_height_cm', 'vehicle_width_cm', 'vehicle_weight_kg',
               'vehicle_length_cm', 'purchase_price', 'purchase_currency']
    
    for field in allowed:
        if field in data:
            if field == 'current_mileage':
                # R2: the client may send "5000" (or junk) — comparing a str to
                # an int below raised TypeError -> 500.
                try:
                    data[field] = int(data[field])
                except (TypeError, ValueError):
                    return jsonify({
                        'error': 'Mileage must be a number',
                        'message_key': 'validation.invalidNumber',
                    }), 400
                # Allow correcting mileage, but not below highest recorded entry
                max_recorded = _get_max_recorded_odometer(current_user.id, vehicle_id)
                if data[field] < max_recorded:
                    return jsonify({
                        'error': f'Mileage cannot be lower than the highest recorded entry ({max_recorded})',
                        'message_key': 'vehicles.mileageBelowRecordedMax',
                        'min_allowed_mileage': max_recorded,
                    }), 400
            if field == 'vin':
                # R1: same '' → None coercion create does, so clearing the VIN
                # stores NULL (distinct under UNIQUE) instead of colliding on ''.
                setattr(vehicle, field, data[field] or None)
                continue
            setattr(vehicle, field, data[field])

    # A price saved without a currency is in the owner's, as at create.
    if data.get('purchase_price') is not None and not vehicle.purchase_currency:
        vehicle.purchase_currency = current_user.chosen_currency

    # F23 — purchase_date needs the same ISO parse used at create.
    if 'purchase_date' in data:
        raw = data['purchase_date']
        try:
            vehicle.purchase_date = datetime.fromisoformat(raw).date() if raw else None
        except (TypeError, ValueError):
            # R2: an unparseable date raised ValueError -> 500.
            return jsonify({
                'error': 'Invalid date format',
                'message_key': 'validation.invalidDate',
            }), 400

    # F31 — per-vehicle wear-interval overrides, strictly validated.
    if 'maintenance_intervals' in data:
        raw = data['maintenance_intervals']
        if raw is None:
            vehicle.maintenance_intervals = None
        elif not isinstance(raw, dict):
            return jsonify({'error': 'maintenance_intervals must be an object'}), 400
        else:
            cleaned = {}
            for key, val in raw.items():
                if key not in MAINTENANCE_INTERVALS:
                    return jsonify({'error': f'Unknown maintenance component: {key}'}), 400
                if (not isinstance(val, (int, float)) or isinstance(val, bool)
                        or not (0 < val <= 500000)):
                    return jsonify({'error': f'Invalid interval for {key}: must be a positive number ≤ 500000'}), 400
                cleaned[key] = int(val)
            vehicle.maintenance_intervals = cleaned or None

    try:
        commit_mutation()
    except IntegrityError as exc:
        db.session.rollback()
        if 'vin' not in str(getattr(exc, 'orig', exc)).lower():
            raise
        return jsonify({
            'error': 'A vehicle with this VIN already exists',
            'message_key': 'vehicles.vinAlreadyExists',
        }), 409

    return jsonify({
        'message': 'Vehicle updated',
        'vehicle': vehicle.to_dict()
    })


@vehicles_bp.route('/<int:vehicle_id>', methods=['DELETE'])
@token_required
@mutation_endpoint(Vehicle, 'vehicle_id')
def delete_vehicle(current_user, vehicle_id):
    """Delete a vehicle (soft delete by default)."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    # Check if hard delete requested
    hard_delete = request.args.get('hard', 'false').lower() == 'true'
    
    if hard_delete:
        from app.services.deletion import DeletionConflict, delete_owned_data, finish_cleanup
        try:
            operation_id = delete_owned_data(current_user.id, vehicle_id=vehicle_id)
        except DeletionConflict as exc:
            db.session.rollback()
            return jsonify({'error': str(exc)}), 409
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Vehicle deletion could not be confirmed')
            return jsonify({'error': 'Could not confirm vehicle deletion. Refresh before retrying; files are retained unless deletion committed.'}), 500
        return jsonify({'message': 'Vehicle deleted', 'cleanup': finish_cleanup(operation_id)})

    # Soft delete = archive (F21 — previously set a phantom `is_active`
    # attribute and persisted nothing while claiming "Vehicle deleted").
    if not vehicle.archived:
        _archive_vehicle(vehicle)
    commit_mutation()

    return jsonify({
        'message': 'Vehicle archived',
        'archived': True,
        'vehicle': vehicle.to_dict(),
    })


@vehicles_bp.route('/reorder', methods=['POST'])
@token_required
def reorder_vehicles(current_user):
    """Reorder vehicles for dashboard display.
    
    Expects JSON body: { "order": [id1, id2, id3, ...] }
    where the array contains vehicle IDs in the desired display order.
    """
    data = request.get_json()
    
    if not data or 'order' not in data:
        return jsonify({'error': 'Order array is required'}), 400
    
    order = data['order']
    
    if not isinstance(order, list):
        return jsonify({'error': 'Order must be an array of vehicle IDs'}), 400
    
    # Validate all IDs belong to current user
    user_vehicle_ids = set(
        v.id for v in Vehicle.query.filter_by(user_id=current_user.id).all()
    )
    
    for vehicle_id in order:
        if not isinstance(vehicle_id, int):
            return jsonify({'error': 'All IDs must be integers'}), 400
        if vehicle_id not in user_vehicle_ids:
            return jsonify({'error': f'Vehicle {vehicle_id} not found or not owned by user'}), 404
    
    # Update display_order for each vehicle
    for idx, vehicle_id in enumerate(order):
        vehicle = db.session.get(Vehicle, vehicle_id)
        if vehicle:
            vehicle.display_order = idx
    
    db.session.commit()
    
    return jsonify({
        'message': 'Vehicles reordered successfully',
        'order': order
    })


@vehicles_bp.route('/<int:vehicle_id>/stats', methods=['GET'])
@token_required
def get_vehicle_stats(current_user, vehicle_id):
    """Get statistics for a vehicle."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    today = utc_today()

    display_ccy = (current_user.currency or 'GBP').upper()
    rates = get_rates_cached(current_app._get_current_object())
    rows = load_expenses([vehicle_id], end=today)
    lifetime = aggregate(rows, display_ccy, rates, end=today)
    ytd = aggregate(rows, display_ccy, rates, start=date(today.year, 1, 1), end=today)
    monthly = aggregate(rows, display_ccy, rates, start=today.replace(day=1), end=today)
    insurance_policies = InsurancePolicy.query.filter_by(vehicle_id=vehicle_id).all()
    annualized = annualized_total(insurance_policies, display_ccy, rates, today)

    # ------------------------------------------------------------------
    # AVERAGE FUEL CONSUMPTION (L/100km)
    # Distance-weighted canonical consumption from full-to-full windows.
    # ------------------------------------------------------------------
    from app.services.fuel_efficiency import weighted_efficiency_query
    avg_consumption = weighted_efficiency_query(
        FuelEntry.vehicle_id == vehicle_id, FuelEntry.user_id == current_user.id)
    # Missing full-to-full observations cannot be replaced with partial-fill or
    # consecutive-odometer guesses. Existing caches can be rebuilt explicitly.

    # Next service due — the soonest of: an upcoming reminder, a future-dated
    # service entry, or a past service's next_due_date pointer.
    #
    # R4-07: all three compared a `Date` column against `now` (a *datetime*), so
    # `(due - now).days` raised TypeError. Three `except Exception: pass`
    # wrappers hid it, and the partially-assigned state meant the response
    # carried a date and a title but next_service_days was ALWAYS null. Compare
    # against `today` (line 449) — same type as the columns.
    from app.models.reminder import Reminder

    def _service_label(*candidates):
        """First non-empty label, with type tokens humanized ('oil_change' ->
        'oil change'), matching how services/due.py labels the same rows.

        Returns None when the entry carries no label of its own: the PWA then
        renders its OWN localized fallback (alerts.serviceDue, already shipped
        in en/ro/es) instead of a server-invented English string.
        """
        for candidate in candidates:
            if candidate:
                return str(candidate).replace('_', ' ')
        return None

    next_service_candidates = []

    upcoming_reminder = Reminder.query.filter_by(
        vehicle_id=vehicle_id,
        completed=False,
        dismissed=False,
    ).filter(
        Reminder.due_date >= today
    ).order_by(Reminder.due_date.asc()).first()
    if upcoming_reminder:
        # A reminder title is the user's own free text — never humanized.
        next_service_candidates.append((upcoming_reminder.due_date, upcoming_reminder.title))

    future_service = ServiceEntry.query.filter(
        ServiceEntry.vehicle_id == vehicle_id,
        ServiceEntry.date >= today,
    ).order_by(ServiceEntry.date.asc()).first()
    if future_service:
        next_service_candidates.append((
            future_service.date,
            _service_label(future_service.title, future_service.service_type),
        ))

    service_with_next_due = ServiceEntry.query.filter(
        ServiceEntry.vehicle_id == vehicle_id,
        ServiceEntry.next_due_date.isnot(None),
        ServiceEntry.next_due_date >= today,
    ).order_by(ServiceEntry.next_due_date.asc()).first()
    if service_with_next_due:
        next_service_candidates.append((
            service_with_next_due.next_due_date,
            _service_label(service_with_next_due.title, service_with_next_due.service_type),
        ))

    next_service = None
    next_service_title = None
    next_service_days = None
    if next_service_candidates:
        # Ties keep the first source listed (reminder > scheduled > next-due),
        # matching the original strictly-earlier comparison.
        due_date, next_service_title = min(next_service_candidates, key=lambda candidate: candidate[0])
        next_service = due_date.isoformat()
        next_service_days = (due_date - today).days

    return jsonify({
        'vehicle_id': vehicle_id,
        'distance_unit': vehicle.distance_unit or 'km',
        'fuel_economy_unit': 'L/100km',
        **{k: lifetime[k] for k in ('basis', 'basis_label', 'as_of', 'start_date', 'end_date',
                                    'display_currency', 'converted', 'fx_applied', 'unconverted')},
        'totals': lifetime['totals'],
        'recorded_total': lifetime['recorded_total'],
        'insurance_estimate': lifetime['insurance_estimate'],
        'total_costs': lifetime['totals']['grand_total'],
        'ytd_spent': ytd['totals']['grand_total'],
        'costs_this_month': monthly['totals']['grand_total'],
        'monthly_insurance_cost': monthly['insurance_estimate'],
        'fuel_costs': lifetime['totals']['fuel'],
        'ytd_fuel_costs': ytd['totals']['fuel'],
        'service_costs': lifetime['totals']['service'],
        'repair_costs': lifetime['totals']['repair'],
        'parking_costs': lifetime['totals']['parking'],
        'parking_ytd_cost': ytd['totals']['parking'],
        'consumable_costs': lifetime['totals']['consumable'],
        'tax_costs': ytd['totals']['tax'],
        'insurance_costs': ytd['insurance_estimate'],
        'insurance_annual_cost': annualized['insurance_estimate'],
        'insurance_annual_converted': annualized['converted'],
        'service_count': lifetime['entry_counts']['service'],
        'repair_count': lifetime['entry_counts']['repair'],
        'fuel_count': lifetime['entry_counts']['fuel'],
        'insurance_count': len(insurance_policies),
        'avg_consumption': float(avg_consumption) if avg_consumption else None,
        'next_service': next_service,
        'next_service_title': next_service_title,
        'next_service_days': next_service_days,
    })


@vehicles_bp.route('/<int:vehicle_id>/expenses-summary', methods=['GET'])
@token_required
def get_expenses_summary(current_user, vehicle_id):
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=current_user.id).first()
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    from app.services.expense_views import period_bounds, available_years
    from app.services.expense_ledger import CATEGORIES
    try:
        start, end = period_bounds(request.args.get('year', utc_today().year), request.args.get('month'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid year or month'}), 400
    currency = (current_user.currency or 'GBP').upper()
    rows = load_expenses([vehicle.id], start, end)
    ledger = aggregate(rows, currency,
                       get_rates_cached(current_app._get_current_object()), start, end)
    ledger['available_years'] = available_years(vehicle.id)
    ledger['categories'] = list(CATEGORIES)
    ledger['available_months'] = [int(row['month'][5:]) for row in ledger['monthly']]
    return jsonify(ledger)


@vehicles_bp.route('/<int:vehicle_id>/expense-records', methods=['GET'])
@token_required
def get_expense_records(current_user, vehicle_id):
    """Filtered source-record pages, separate from complete expense aggregates."""
    from app.services.expense_views import period_bounds, detail_page
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=current_user.id).first()
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    try:
        start, end = period_bounds(request.args.get('year', utc_today().year), request.args.get('month'))
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        if not 1 <= page <= 2147483647 or not 1 <= per_page <= 100:
            raise ValueError('Invalid page')
        result = detail_page(vehicle, current_user, request.args.get('category', 'fuel'),
            start, end, page, per_page, request.args.get('scope', 'period'),
            get_rates_cached(current_app._get_current_object()))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid period, category or pagination'}), 400
    return jsonify(result)


@vehicles_bp.route('/<int:vehicle_id>/cost-analytics', methods=['GET'])
@token_required
def get_cost_analytics(current_user, vehicle_id):
    """Cost-per-distance trend over time + a deterministic 12-month cost forecast.

    Aggregates the owner's own entries server-side and projects future cost via
    least-squares linear
    regression over complete months. Distance per month is derived from monotonic
    (running-max) odometer deltas, so cost-per-distance is only reported for
    months where real distance is known.

    F24 — the response also carries an ``ownership`` object (or ``None`` when no
    purchase_price is stored)::

        ownership: {
            purchase_price:  float,          # original amount in purchase_currency
            purchase_date:   'YYYY-MM-DD' | None,
            months_owned:    int | None,     # purchase_date → today
            total_with_purchase: float,      # running total_cost + purchase_price
            cost_per_distance_with_purchase: float | None,  # same span guard as
                                             # cost_per_distance_lifetime
            avg_monthly_ownership: float | None,
        }
    """
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=current_user.id).first()
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404

    today = utc_today()
    MONTHS = 12  # size of the displayed trend window

    # --- Build the trailing month buckets (oldest -> newest, ending this month).
    buckets = []
    y, m = today.year, today.month
    for _ in range(MONTHS):
        buckets.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    buckets.reverse()

    def month_key(yy, mm):
        return f'{yy:04d}-{mm:02d}'

    def month_end(yy, mm):
        if mm == 12:
            return date(yy, 12, 31)
        return date(yy, mm + 1, 1) - timedelta(days=1)

    def month_start(yy, mm):
        return date(yy, mm, 1)

    display_ccy = (current_user.currency or 'GBP').upper()
    rates = get_rates_cached(current_app._get_current_object())
    ledger = aggregate(load_expenses([vehicle_id], end=today), display_ccy, rates, end=today)
    fx_converted, fx_applied = ledger['converted'], ledger['fx_applied']
    monthly_cost = {tuple(map(int, row['month'].split('-'))): row['total'] for row in ledger['monthly']}

    # --- Odometer readings over the vehicle's whole history (for distance deltas).
    odo_points = (
        db.session.query(Entry.date, Entry.odometer)
        .filter(
            Entry.vehicle_id == vehicle_id,
            Entry.odometer.isnot(None),
            Entry.odometer > 0,
            Entry.date <= today,
        )
        .order_by(Entry.date.asc())
        .all()
    )

    def max_odo_through(end_date):
        """Largest odometer reading on/before end_date (running max = monotonic)."""
        best = None
        for d, odo in odo_points:
            if d <= end_date and (best is None or odo > best):
                best = odo
        return best

    # Baseline odometer just before the window starts (for the first bucket's delta).
    first_start = month_start(*buckets[0])
    prev_cum = None
    for d, odo in odo_points:
        if d < first_start and (prev_cum is None or odo > prev_cum):
            prev_cum = odo

    series = []
    for (yy, mm) in buckets:
        cost = round(monthly_cost.get((yy, mm), 0.0), 2)
        cum = max_odo_through(month_end(yy, mm))
        distance = None
        cost_per_distance = None
        if cum is not None and prev_cum is not None:
            d = cum - prev_cum
            if d > 0:
                distance = int(d)
                cost_per_distance = round(cost / d, 4) if fx_converted else None
        if cum is not None:
            prev_cum = cum if (prev_cum is None or cum > prev_cum) else prev_cum
        series.append({
            'month': month_key(yy, mm),
            'cost': cost,
            'distance': distance,
            'cost_per_distance': cost_per_distance,
        })

    total_cost = ledger['totals']['grand_total']
    total_distance = None
    cost_per_distance_lifetime = None
    span = 0
    if odo_points:
        odo_values = [o for _, o in odo_points]
        span = max(odo_values) - min(odo_values)
        if span > 0:
            total_distance = int(span)
            cost_per_distance_lifetime = round(total_cost / span, 4) if fx_converted else None

    # A stored purchase currency is independent of the display preference; a price
    # stored without one (older vehicles) is in the owner's currency.
    ownership = None
    if vehicle.purchase_price is not None:
        from dateutil.relativedelta import relativedelta
        purchase = float(vehicle.purchase_price)
        months_owned = None
        if vehicle.purchase_date:
            delta = relativedelta(today, vehicle.purchase_date)
            months_owned = max(0, delta.years * 12 + delta.months)
        purchase_currency = vehicle.purchase_price_currency
        converted_purchase = convert(purchase, purchase_currency, display_ccy, rates)
        total_with_purchase = (round(total_cost + float(converted_purchase), 2)
                               if converted_purchase is not None and fx_converted else None)
        ownership = {
            'purchase_price': purchase,
            'purchase_currency': purchase_currency,
            'purchase_price_display': float(converted_purchase) if converted_purchase is not None else None,
            'purchase_converted': converted_purchase is not None,
            'purchase_date': vehicle.purchase_date.isoformat() if vehicle.purchase_date else None,
            'months_owned': months_owned,
            'total_with_purchase': total_with_purchase,
            'cost_per_distance_with_purchase':
                round(total_with_purchase / span, 4) if span > 0 and total_with_purchase is not None else None,
            'avg_monthly_ownership':
                round(total_with_purchase / max(1, months_owned), 2)
                if months_owned is not None and total_with_purchase is not None else None,
        }

    # --- Forecast: least-squares linear regression over COMPLETE months.
    # Exclude the current (incomplete) month and any leading zero-cost months
    # before the vehicle's first recorded expense.
    forecast = None
    complete = series[:-1]  # drop current in-progress month
    # Trim leading months with no cost AND no prior history.
    first_nonzero = next((i for i, s in enumerate(complete) if s['cost'] > 0), None)
    if first_nonzero is not None and fx_converted:
        hist = complete[first_nonzero:]
        costs = [s['cost'] for s in hist]
        n = len(costs)
        if n >= 3:
            xs = list(range(n))
            mean_x = sum(xs) / n
            mean_y = sum(costs) / n
            denom = sum((x - mean_x) ** 2 for x in xs)
            slope = (sum((x - mean_x) * (yv - mean_y) for x, yv in zip(xs, costs)) / denom) if denom else 0.0
            intercept = mean_y - slope * mean_x

            projected = []
            ny, nm = today.year, today.month
            running_total = 0.0
            for k in range(1, 13):
                # advance one month
                nm += 1
                if nm == 13:
                    nm, ny = 1, ny + 1
                val = intercept + slope * (n - 1 + k)
                val = max(0.0, round(val, 2))
                running_total += val
                projected.append({'month': month_key(ny, nm), 'projected_cost': val})

            # Trend classification relative to the historical average.
            if mean_y > 0 and abs(slope) > 0.02 * mean_y:
                trend = 'up' if slope > 0 else 'down'
            else:
                trend = 'flat'

            forecast = {
                'avg_monthly': round(mean_y, 2),
                'projected_next_12_total': round(running_total, 2),
                'trend': trend,
                'method': 'linear_regression',
                'basis': 'forecast_from_recorded_expenses_and_scheduled_insurance',
                'months_of_history': n,
                'monthly': projected,
            }

    return jsonify({
        'distance_unit': vehicle.distance_unit or 'km',
        'currency': display_ccy,           # kept for backward compatibility
        'display_currency': display_ccy,
        'converted': fx_converted,         # False → a rate was unavailable
        'fx_applied': fx_applied,          # True → totals crossed currencies
        **{k: ledger[k] for k in ('basis', 'basis_label', 'as_of', 'start_date', 'end_date', 'unconverted', 'totals', 'recorded_total', 'insurance_estimate')},
        'series': series,
        'cost_per_distance_lifetime': cost_per_distance_lifetime,
        'total_cost': round(total_cost, 2),
        'total_distance': total_distance,
        'ownership': ownership,            # F24 — None when no purchase_price
        'forecast': forecast,
    })


def _forecast_recur_step(recurrence_type):
    """relativedelta step for a recurrence type (mirrors the tax/parking generators)."""
    from dateutil.relativedelta import relativedelta
    return {
        'daily': relativedelta(days=1),
        'weekly': relativedelta(weeks=1),
        'monthly': relativedelta(months=1),
        'quarterly': relativedelta(months=3),
        'semi_annual': relativedelta(months=6),
        'semi-annual': relativedelta(months=6),
        'annual': relativedelta(years=1),
        'yearly': relativedelta(years=1),
    }.get((recurrence_type or 'monthly'), relativedelta(months=1))


def _build_forecast(user, vehicles, months=12, today=None):
    """F11 — project the next ``months`` of cost per month for ``vehicles``.

    Sums forward-dated recurring taxes and parking permits (advanced by their
    recurrence step) and insurance premiums normalized to a monthly figure (F12's
    ``annualized_premium`` / 12, spread across the months each policy is active).
    Every amount is converted into the user's display currency (F1).

    Strictly owner-scoped: callers pass only the user's own vehicles. Returns a
    JSON-able dict.
    """
    from datetime import date as _date
    from dateutil.relativedelta import relativedelta
    from app.models import TaxEntry, ParkingEntry
    from app.models.insurance import InsurancePolicy

    today = today or datetime.now(timezone.utc).date()
    months = max(1, min(int(months or 12), 24))

    vids = [v.id for v in vehicles]
    display_ccy = (getattr(user, 'currency', None) or 'GBP').upper()
    rates = get_rates_cached(current_app._get_current_object())

    # Ordered month buckets starting at the current month.
    first = _date(today.year, today.month, 1)
    keys = []
    cursor = first
    for _ in range(months):
        keys.append((cursor.year, cursor.month))
        cursor = cursor + relativedelta(months=1)
    window_end = cursor - timedelta(days=1)          # last day of the final bucket
    index = {k: i for i, k in enumerate(keys)}

    buckets = [{'tax': 0.0, 'insurance': 0.0, 'parking': 0.0} for _ in keys]
    fx_applied = False
    converted = True

    def add(amount, from_ccy, kind, monthkey):
        nonlocal fx_applied, converted
        i = index.get(monthkey)
        if i is None:
            return
        conv = convert(amount, from_ccy, display_ccy, rates)
        if conv is None:
            converted = False
        else:
            buckets[i][kind] += float(conv)
        if amount and (from_ccy or '').upper() != display_ccy:
            fx_applied = True

    def _project(entry, kind):
        """Advance a recurring entry from its next_due_date across the window."""
        step = _forecast_recur_step(getattr(entry, 'recurrence_type', None))
        occ = entry.next_due_date
        guard = 0
        while occ and occ <= window_end and guard < 500:
            if occ >= first:
                add(entry.amount, entry.currency, kind, (occ.year, occ.month))
            occ = occ + step
            guard += 1

    if vids:
        # --- Recurring taxes ---
        for tx in TaxEntry.query.filter(
            TaxEntry.vehicle_id.in_(vids),
            TaxEntry.recurring == True,            # noqa: E712
            TaxEntry.next_due_date.isnot(None),
        ).all():
            _project(tx, 'tax')

        # --- Recurring parking permits ---
        for pk in ParkingEntry.query.filter(
            ParkingEntry.vehicle_id.in_(vids),
            ParkingEntry.recurring == True,        # noqa: E712
            ParkingEntry.next_due_date.isnot(None),
        ).all():
            _project(pk, 'parking')

        # --- Insurance: monthly-normalized premium spread across active months (F12) ---
        for p in InsurancePolicy.query.filter(
            InsurancePolicy.vehicle_id.in_(vids),
            InsurancePolicy.status == 'active',
        ).all():
            monthly = p.annualized_premium / 12.0
            if not monthly or not p.start_date:
                continue
            for (yy, mm) in keys:
                m_start = _date(yy, mm, 1)
                m_end = (m_start + relativedelta(months=1)) - timedelta(days=1)
                if p.start_date <= m_end and (p.end_date is None or p.end_date >= m_start):
                    add(monthly, p.currency, 'insurance', (yy, mm))

    # Monthly budget = sum of the vehicles' monthly_budget (already display currency).
    budgets = [float(v.monthly_budget) for v in vehicles if v.monthly_budget is not None]
    monthly_budget = round(sum(budgets), 2) if budgets else None

    out = []
    for i, (yy, mm) in enumerate(keys):
        b = buckets[i]
        total = round(b['tax'] + b['insurance'] + b['parking'], 2)
        out.append({
            'month': f'{yy:04d}-{mm:02d}',
            'projected': total,
            'breakdown': {k: round(v, 2) for k, v in b.items()},
            'over_budget': monthly_budget is not None and total > monthly_budget,
        })

    return {
        'currency': display_ccy,
        'display_currency': display_ccy,
        'months': months,
        'monthly_budget': monthly_budget,
        'converted': converted,      # False → a needed FX rate was unavailable
        'fx_applied': fx_applied,    # True → amounts crossed currencies
        'basis': 'forecast_with_monthly_annualized_insurance',
        'buckets': out,
    }


@vehicles_bp.route('/<int:vehicle_id>/forecast', methods=['GET'])
@token_required
def get_vehicle_forecast(current_user, vehicle_id):
    """12-month forward cost forecast for one vehicle (F11)."""
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=current_user.id).first()
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    months = request.args.get('months', 12, type=int)
    return jsonify(_build_forecast(current_user, [vehicle], months))


@vehicles_bp.route('/<int:vehicle_id>/timeline', methods=['GET'])
@token_required
def get_vehicle_timeline(current_user, vehicle_id):
    """Get paginated timeline of all entries for a vehicle.

    Query params:
      page      – 1-based page number (default 1)
      per_page  – items per page, 10–200 (default 50)
      type      – entry type filter: all | fuel | service | repair | tax |
                  parking | reminder | todo | insurance (default all)
    """
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()

    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404

    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(10, request.args.get('per_page', 50, type=int)), 200)

    _VALID_TYPES = {
        'all', 'fuel', 'service', 'repair', 'tax',
        'parking', 'consumable', 'reminder', 'todo', 'insurance',
    }
    entry_type = request.args.get('type', 'all').strip().lower()
    if entry_type not in _VALID_TYPES:
        entry_type = 'all'

    include_insurance = entry_type in ('all', 'insurance')

    # ------------------------------------------------------------------
    # Insurance policies — always a small set (< ~20 per vehicle).
    # Safe to fetch all without risk of OOM.
    # ------------------------------------------------------------------
    insurance_items = []
    insurance_total = 0
    if include_insurance:
        try:
            from app.models.insurance import InsurancePolicy
            ins_query = InsurancePolicy.query.filter_by(vehicle_id=vehicle_id)
            insurance_total = ins_query.count()
            # Only include insurance records on page 1 to avoid duplicating
            # them across pages. (They're interleaved by date in the merge.)
            if page == 1:
                for policy in ins_query.order_by(InsurancePolicy.start_date.desc()).all():
                    premium   = float(policy.premium or 0)
                    frequency = policy.payment_frequency or 'annual'
                    # F12: single-source annualization (premium × frequency).
                    annual_cost = policy.annualized_premium
                    insurance_items.append({
                        'id':               policy.id,
                        'type':             'insurance',
                        'title':            policy.provider,
                        'description':      f"{policy.provider} - {policy.policy_number or 'Policy'}",
                        'amount':           premium,
                        'cost':             premium,
                        'currency':         policy.currency,
                        'annual_cost':      annual_cost,
                        'payment_frequency': frequency,
                        'date':             policy.start_date.isoformat() if policy.start_date else None,
                        'vehicle_id':       policy.vehicle_id,
                        'created_at':       isoformat_utc(policy.created_at) if policy.created_at else None,
                        'policy_type':      policy.policy_type,
                        'status':           policy.status,
                    })
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Entries — DB-level count + paginated fetch. No .all(), no OOM.
    # ------------------------------------------------------------------
    entry_total = 0
    result_items = []

    if entry_type == 'insurance':
        # Pure insurance view — paginate the small in-memory list.
        insurance_items.sort(key=lambda x: x.get('date') or '', reverse=True)
        start = (page - 1) * per_page
        result_items = insurance_items[start:start + per_page]
        total = insurance_total
        nav_total = insurance_total   # insurance is what we paginate here

    else:
        eq = Entry.query.filter_by(vehicle_id=vehicle_id)
        if entry_type != 'all':
            eq = eq.filter(Entry.type == entry_type)

        entry_total = eq.count()

        # M2: paginate ENTRIES ONLY — plain offset/limit, no insurance splicing.
        # The old buffer/offset arithmetic (db_offset = (page-1)*per_page -
        # insurance_total) both dropped policies that sorted past page 1's cut
        # and re-served page-1 entries on later pages. Insurance is a small
        # (< ~20) set delivered whole on page 1 (below) and merged client-side,
        # so it can never displace or duplicate an entry row again.
        entries_raw = (
            eq
            .order_by(Entry.date.desc(), Entry.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        result_items = [e.to_dict(include_attachments=False) for e in entries_raw]

        # Displayed count includes policies (they render in the same feed), but
        # page navigation tracks ENTRIES only: every policy already ships on
        # page 1, so has_next/pages must not count them or the client would be
        # told to fetch an entry page that doesn't exist.
        total = entry_total + insurance_total
        nav_total = entry_total

    pages = max(1, (nav_total + per_page - 1) // per_page)

    response = {
        'entries':      result_items,
        'total':        total,
        'pages':        pages,
        'current_page': page,
        'per_page':     per_page,
        'has_next':     page < pages,
        'has_prev':     page > 1,
    }
    # Page 1 of the combined 'all' feed carries the full (small) insurance set
    # under its own key so the client merges it in without any per-page
    # splicing. Absent on later pages and on filtered views (M2).
    if entry_type == 'all' and page == 1:
        response['insurance'] = insurance_items

    return jsonify(response)


@vehicles_bp.route('/<int:vehicle_id>/mileage', methods=['POST'])
@token_required
@mutation_endpoint(Vehicle, 'vehicle_id')
def update_mileage(current_user, vehicle_id):
    """Update vehicle mileage."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    data = request.get_json()

    # R4-11: `if not new_mileage` rejected a legitimate 0 (a vehicle with no
    # entries yet, or an odometer that has been replaced), and the comparison
    # below raised TypeError on the string a number input submits.
    try:
        new_mileage = parse_optional_int(data.get('mileage'),
                                         'Mileage must be a number')
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    if new_mileage is None:
        return jsonify({'error': 'Mileage is required',
                        'message_key': REQUIRED_FIELD_KEY}), 400

    max_recorded_odometer = _get_max_recorded_odometer(current_user.id, vehicle.id)
    if new_mileage < max_recorded_odometer:
        return jsonify({
            'error': f'Mileage cannot be lower than the highest recorded entry ({max_recorded_odometer})',
            'message_key': 'vehicles.mileageBelowRecordedMax',
            'min_allowed_mileage': max_recorded_odometer,
        }), 400
    
    vehicle.current_mileage = new_mileage
    commit_mutation()
    
    return jsonify({
        'message': 'Mileage updated',
        'message_key': 'vehicles.mileageUpdated',
        'revision': vehicle.revision,
        'current_mileage': vehicle.current_mileage
    })


def _currency_review_payload(user):
    return {'account_currency': user.chosen_currency, 'groups': currency_review.review_groups(user)}


@vehicles_bp.route('/currency-review', methods=['GET'])
@token_required
def get_currency_review(current_user):
    """Records still labelled with a built-in currency, for the person to confirm or correct."""
    return jsonify(_currency_review_payload(current_user))


@vehicles_bp.route('/currency-review', methods=['POST'])
@token_required
def resolve_currency_review(current_user):
    data = request.get_json(silent=True) or {}
    currency, action = data.get('currency'), data.get('action')
    resolve = CURRENCY_REVIEW_ACTIONS.get(action)
    open_currencies = {group['currency'] for group in currency_review.review_groups(current_user)}
    if resolve is None or currency not in open_currencies:
        return jsonify({'error': 'There are no records to review in that currency.',
                        'message_key': 'currencyReview.nothingToReview'}), 400
    relabelled = resolve(current_user, currency) or 0
    return jsonify({**_currency_review_payload(current_user), 'relabelled': relabelled})


@vehicles_bp.route('/recent-transactions', methods=['GET'])
@token_required
def get_recent_transactions(current_user):
    """Most recent cost-bearing transactions across the user's whole fleet.

    Merges the polymorphic Entry table (fuel / service / repair / tax / parking /
    consumable) with insurance policies, newest-first, capped to `limit`. Every
    item is enriched with its vehicle name so the dashboard can label and deep-link
    each row to the vehicle timeline. Ownership is enforced by scoping to the
    current user's vehicles — a user can never see another user's entries.

    Query params:
      limit – number of transactions to return, 1–20 (default 5)
    """
    limit = min(max(1, request.args.get('limit', 5, type=int)), 20)

    # Map of the current user's vehicles → display name (make/model fallback).
    # Small per-user set; also serves as the ownership allow-list for entries.
    vehicles = Vehicle.query.filter_by(user_id=current_user.id).all()
    if not vehicles:
        return jsonify({'transactions': []})
    vehicle_names = {
        v.id: (v.name or f"{v.make or ''} {v.model or ''}".strip() or 'Vehicle')
        for v in vehicles
    }
    vehicle_ids = list(vehicle_names.keys())

    # Only cost-bearing entry types are "transactions" (reminders/todos excluded).
    _TX_TYPES = ('fuel', 'service', 'repair', 'tax', 'parking', 'consumable')

    # "Recent" = already happened. Exclude future-dated entries (e.g. a scheduled
    # MOT/inspection logged for next year) — those belong in reminders/upcoming,
    # not the recent-spending feed.
    today = datetime.now(timezone.utc).date()

    def _iso(d):
        return d.isoformat() if d else None

    items = []

    # --- Entry-table transactions (single query, DB-ordered, bounded) ---
    entries = (
        Entry.query
        .filter(Entry.vehicle_id.in_(vehicle_ids), Entry.type.in_(_TX_TYPES),
                Entry.date <= today)
        .order_by(Entry.date.desc(), Entry.id.desc())
        .limit(limit)
        .all()
    )
    for e in entries:
        d = e.to_dict(include_attachments=False)
        items.append({
            'id':           d.get('id'),
            'type':         d.get('type'),
            'title':        d.get('title'),
            'description':  d.get('description') or d.get('title'),
            'cost':         d.get('cost') if d.get('cost') is not None else d.get('amount'),
            'currency':     d.get('currency'),
            'date':         d.get('date'),
            'created_at':   d.get('created_at'),
            'vehicle_id':   d.get('vehicle_id'),
            'vehicle_name': vehicle_names.get(d.get('vehicle_id'), 'Vehicle'),
        })

    # --- Insurance (separate model) merged into the same feed ---
    try:
        from app.models.insurance import InsurancePolicy
        policies = (
            InsurancePolicy.query
            .filter(InsurancePolicy.user_id == current_user.id,
                    InsurancePolicy.vehicle_id.in_(vehicle_ids),
                    InsurancePolicy.start_date <= today)
            .order_by(InsurancePolicy.start_date.desc(), InsurancePolicy.id.desc())
            .limit(limit)
            .all()
        )
        for p in policies:
            items.append({
                'id':           p.id,
                'type':         'insurance',
                'title':        p.provider,
                'description':  f"{p.provider} - {p.policy_number}" if p.policy_number else p.provider,
                # F12: recent-transactions still shows the per-payment premium as
                # booked; payment_frequency + annual_cost let the UI label it.
                'cost':         float(p.premium) if p.premium is not None else None,
                'payment_frequency': p.payment_frequency,
                'annual_cost':  p.annualized_premium,
                'currency':     p.currency,
                'date':         _iso(p.start_date),
                'created_at':   _iso(p.created_at),
                'vehicle_id':   p.vehicle_id,
                'vehicle_name': vehicle_names.get(p.vehicle_id, 'Vehicle'),
            })
    except Exception:
        current_app.logger.exception('recent-transactions: insurance merge failed')

    # Newest-first across both sources; break date ties with created_at then id.
    items.sort(
        key=lambda x: (x.get('date') or '', x.get('created_at') or '', x.get('id') or 0),
        reverse=True,
    )

    return jsonify({'transactions': items[:limit]})


@vehicles_bp.route('/summary', methods=['GET'])
@token_required
def get_vehicles_summary(current_user):
    """Get summary of all vehicles."""
    # NOTE: the Vehicle model has no `is_active` column (it uses `archived`);
    # the previous filter_by(is_active=True) raised. Scope to non-archived here.
    vehicles = Vehicle.query.filter_by(
        user_id=current_user.id,
        archived=False
    ).all()
    vehicle_ids = [v.id for v in vehicles]

    display_ccy = (current_user.currency or 'GBP').upper()
    rates = get_rates_cached(current_app._get_current_object())
    ledger = aggregate(load_expenses(vehicle_ids), display_ccy, rates)
    total_fuel = float(db.session.query(func.coalesce(func.sum(FuelEntry.liters), 0))
        .filter(FuelEntry.vehicle_id.in_(vehicle_ids), FuelEntry.date <= utc_today()).scalar() or 0)

    return jsonify({
        'vehicle_count': len(vehicles),
        'total_cost': ledger['totals']['grand_total'],
        'total_fuel_volume': round(total_fuel, 2),
        'currency': display_ccy,           # kept for backward compatibility
        'display_currency': display_ccy,
        **{k: ledger[k] for k in ('basis', 'basis_label', 'as_of', 'start_date', 'end_date', 'converted', 'fx_applied', 'unconverted', 'totals', 'recorded_total', 'insurance_estimate')},
        'vehicles': [v.to_dict() for v in vehicles],
    })


@vehicles_bp.route('/<int:vehicle_id>/photo', methods=['POST'])
@token_required
def upload_vehicle_photo(current_user, vehicle_id):
    """Upload a photo for a vehicle."""
    import os
    import uuid
    from werkzeug.utils import secure_filename
    
    # Security constants
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_MIME_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
    # Magic bytes for image type detection
    IMAGE_SIGNATURES = {
        b'\xff\xd8\xff': 'jpg',
        b'\x89PNG\r\n\x1a\n': 'png',
        b'GIF87a': 'gif',
        b'GIF89a': 'gif',
    }
    
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    if 'photo' not in request.files:
        return jsonify({'error': 'No photo provided'}), 400
    
    photo = request.files['photo']
    
    if photo.filename == '':
        return jsonify({'error': 'No photo selected'}), 400
    
    # Check file size
    photo.seek(0, 2)  # Seek to end
    size = photo.tell()
    photo.seek(0)  # Reset to beginning
    
    if size > MAX_FILE_SIZE:
        return jsonify({'error': 'File too large. Maximum size is 10MB'}), 400
    
    # Validate file extension
    filename = secure_filename(photo.filename)
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    # Validate MIME type from content-type header
    if photo.content_type not in ALLOWED_MIME_TYPES:
        return jsonify({'error': 'Invalid file type'}), 400
    
    # Validate actual file content (magic bytes)
    header = photo.read(12)
    photo.seek(0)
    detected_type = None
    for sig, img_type in IMAGE_SIGNATURES.items():
        if header.startswith(sig):
            detected_type = img_type
            break
    # WebP: starts with RIFF....WEBP
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        detected_type = 'webp'
    
    if detected_type is None:
        return jsonify({'error': 'Invalid image file'}), 400
    
    # Create uploads directory with secure permissions
    upload_dir = os.path.join(current_app.root_path, '..', 'uploads', 'vehicles')
    os.makedirs(upload_dir, mode=0o750, exist_ok=True)
    
    # Generate unique filename (prevent path traversal)
    unique_filename = f"{vehicle.id}_{uuid.uuid4().hex}.{detected_type}"
    file_path = os.path.join(upload_dir, unique_filename)
    
    # Ensure file_path is within upload_dir (prevent path traversal)
    if not os.path.abspath(file_path).startswith(os.path.abspath(upload_dir)):
        return jsonify({'error': 'Invalid file path'}), 400
    
    # Delete old photo if exists
    if vehicle.photo:
        old_path = os.path.join(upload_dir, os.path.basename(vehicle.photo))
        if os.path.exists(old_path) and os.path.abspath(old_path).startswith(os.path.abspath(upload_dir)):
            os.remove(old_path)
    
    # Save new photo with secure permissions
    photo.save(file_path)
    os.chmod(file_path, 0o640)  # Owner rw, group r, others none
    
    # Update vehicle record
    vehicle.photo = f"/uploads/vehicles/{unique_filename}"
    db.session.commit()
    
    from app.utils import sign_upload_url
    return jsonify({
        'message': 'Photo uploaded successfully',
        'photo_url': sign_upload_url(vehicle.photo)
    })


@vehicles_bp.route('/<int:vehicle_id>/photo', methods=['DELETE'])
@token_required
def delete_vehicle_photo(current_user, vehicle_id):
    """Delete a vehicle's photo."""
    import os
    
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    if not vehicle.photo:
        return jsonify({'error': 'No photo to delete'}), 404
    
    # Delete file
    upload_dir = os.path.join(current_app.root_path, '..', 'uploads', 'vehicles')
    old_path = os.path.join(upload_dir, os.path.basename(vehicle.photo))
    if os.path.exists(old_path):
        os.remove(old_path)
    
    vehicle.photo = None
    db.session.commit()
    
    return jsonify({'message': 'Photo deleted successfully'})


# CO2 emission factors (kg CO2 per liter of fuel)
CO2_EMISSION_FACTORS = {
    'petrol': 2.31,      # kg CO2/liter
    'gasoline': 2.31,
    'regular': 2.31,
    'premium': 2.31,
    'diesel': 2.68,      # kg CO2/liter
    'e85': 1.61,         # kg CO2/liter (ethanol blend)
    'lpg': 1.51,         # kg CO2/liter
    'cng': 2.75,         # kg CO2/kg (natural gas)
    'electric': 0,       # No direct emissions
    'hybrid': 1.85,      # Estimated average
}

# Benchmark fuel efficiency (L/100km) by vehicle type
BENCHMARK_EFFICIENCY = {
    'petrol': 8.0,
    'gasoline': 8.0,
    'diesel': 6.5,
    'hybrid': 5.0,
    'electric': 0,  # kWh/100km typically 15-20
}


# Standard maintenance intervals in KM (F31 — defaults; per-vehicle overrides
# live in Vehicle.maintenance_intervals, in the vehicle's own distance unit).
MAINTENANCE_INTERVALS = {
    'oil_change': 10000,
    'air_filter': 20000,
    'cabin_filter': 25000,
    'brake_pads': 50000,
    'brake_fluid': 40000,
    'transmission_fluid': 60000,
    'coolant': 50000,
    'spark_plugs': 40000,
    'timing_belt': 100000,
    'tires': 50000,
    'battery': 50000,  # Or 4-5 years
}

_MILES_PER_KM = 0.621371


def _effective_intervals(vehicle):
    """Wear thresholds for one vehicle, in ITS OWN distance unit (F31).

    Starts from the km defaults (converted ×0.621, rounded to the nearest 500,
    for miles vehicles), then overlays the vehicle's stored overrides. Stored
    JSON is never trusted: only known component keys with positive numeric
    values ≤ 500000 are applied.
    """
    is_miles = (vehicle.distance_unit or 'km').lower().startswith('mi')
    intervals = {}
    for key, km in MAINTENANCE_INTERVALS.items():
        if is_miles:
            intervals[key] = max(500, int(round(km * _MILES_PER_KM / 500.0)) * 500)
        else:
            intervals[key] = km
    overrides = vehicle.maintenance_intervals
    if isinstance(overrides, dict):
        for key, val in overrides.items():
            if (key in MAINTENANCE_INTERVALS
                    and isinstance(val, (int, float)) and not isinstance(val, bool)
                    and 0 < val <= 500000):
                intervals[key] = int(val)
    return intervals


@vehicles_bp.route('/<int:vehicle_id>/health', methods=['GET'])
@token_required
def get_vehicle_health(current_user, vehicle_id):
    """Get comprehensive vehicle health data including carbon footprint and maintenance status."""
    from datetime import datetime, timedelta
    from sqlalchemy import func, extract
    
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    now = datetime.now(timezone.utc)
    today = now.date()
    current_year = now.year
    one_year_ago = now - timedelta(days=365)
    six_months_ago = now - timedelta(days=180)
    
    # ------------------------------------------------------------------
    # All-time scalar aggregates — zero rows fetched into Python memory
    # ------------------------------------------------------------------
    total_liters_all_time = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.liters), 0))
        .filter(FuelEntry.vehicle_id == vehicle_id)
        .scalar()
    )
    ytd_liters = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.liters), 0))
        .filter(
            FuelEntry.vehicle_id == vehicle_id,
            extract('year', FuelEntry.date) == current_year,
        )
        .scalar()
    )
    yearly_liters = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.liters), 0))
        .filter(
            FuelEntry.vehicle_id == vehicle_id,
            FuelEntry.date >= one_year_ago.date(),
        )
        .scalar()
    )
    from app.services.fuel_efficiency import weighted_efficiency_query, weighted_efficiency
    from app.utils.units import distance_to_km
    avg_efficiency = weighted_efficiency_query(FuelEntry.vehicle_id == vehicle_id)

    total_distance = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.trip_distance), 0))
        .filter(
            FuelEntry.vehicle_id == vehicle_id,
            FuelEntry.trip_distance.isnot(None),
        )
        .scalar()
    )
    total_distance = float(distance_to_km(total_distance, vehicle.distance_unit) or 0)
    total_fuel_cost = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.total_price), 0))
        .filter(FuelEntry.vehicle_id == vehicle_id)
        .scalar()
    )
    total_service_cost = float(
        db.session.query(func.coalesce(func.sum(ServiceEntry.amount), 0))
        .filter(ServiceEntry.vehicle_id == vehicle_id, ServiceEntry.date <= today)
        .scalar()
    )
    total_repair_cost = float(
        db.session.query(func.coalesce(func.sum(RepairEntry.amount), 0))
        .filter(RepairEntry.vehicle_id == vehicle_id)
        .scalar()
    )

    # ------------------------------------------------------------------
    # Per-entry data — bounded to relevant time windows or capped
    # ------------------------------------------------------------------
    # Last-12-months fuel: for monthly CO2 / cost breakdown
    fuel_year_entries = (
        FuelEntry.query
        .filter(FuelEntry.vehicle_id == vehicle_id, FuelEntry.date >= one_year_ago.date())
        .order_by(FuelEntry.date.desc())
        .all()
    )
    # Most-recent 20 fuel entries: for efficiency trend analysis
    fuel_top20 = (
        FuelEntry.query
        .filter_by(vehicle_id=vehicle_id)
        .order_by(FuelEntry.date.desc())
        .limit(20)
        .all()
    )
    # Service entries: most-recent 500 (years of annual services), ordered desc
    service_entries = (
        ServiceEntry.query
        .filter_by(vehicle_id=vehicle_id)
        .order_by(ServiceEntry.date.desc())
        .limit(500)
        .all()
    )
    # Recent repairs (last 6 months) for frequency check
    recent_repairs = (
        RepairEntry.query
        .filter(
            RepairEntry.vehicle_id == vehicle_id,
            RepairEntry.date >= six_months_ago.date(),
        )
        .order_by(RepairEntry.date.desc())
        .all()
    )
    # All repairs capped at 500 for component-wear keyword matching
    repair_entries = (
        RepairEntry.query
        .filter_by(vehicle_id=vehicle_id)
        .order_by(RepairEntry.date.desc())
        .limit(500)
        .all()
    )
    
    # ============================================
    # CARBON FOOTPRINT TRACKER
    # ============================================
    
    fuel_type = (vehicle.fuel_type or 'petrol').lower()
    emission_factor = CO2_EMISSION_FACTORS.get(fuel_type, 2.31)
    
    # Calculate total CO2 emissions  (from DB aggregate — no row iteration)
    total_co2_all_time = total_liters_all_time * emission_factor  # kg

    # YTD emissions (from DB aggregate)
    ytd_co2 = ytd_liters * emission_factor

    # Last 12 months emissions (from DB aggregate)
    yearly_co2 = yearly_liters * emission_factor

    # Monthly breakdown for chart (last 12 months) — bounded fetch
    monthly_emissions = {}
    for e in fuel_year_entries:
        if e.date:
            key = e.date.strftime('%Y-%m')
            liters = float(e.liters or 0)
            monthly_emissions[key] = monthly_emissions.get(key, 0) + (liters * emission_factor)
    
    # Calculate eco-driving score (0-100) — uses DB-level avg_efficiency
    benchmark = BENCHMARK_EFFICIENCY.get(fuel_type, 8.0)
    eco_score = 50  # Default
    if avg_efficiency and benchmark > 0:
        # Score based on how close to or better than benchmark
        ratio = benchmark / avg_efficiency  # Higher is better
        eco_score = min(100, max(0, int(ratio * 60 + 20)))
    
    # CO2 per km  (total_distance is already a DB aggregate scalar)
    co2_per_km = (total_co2_all_time / total_distance * 1000) if total_distance > 0 else None  # grams/km
    
    # Carbon offset recommendations
    trees_needed_yearly = yearly_co2 / 21  # Average tree absorbs ~21kg CO2/year
    
    carbon_footprint = {
        'total_co2_kg': round(total_co2_all_time, 1),
        'ytd_co2_kg': round(ytd_co2, 1),
        'yearly_co2_kg': round(yearly_co2, 1),
        'co2_per_km_grams': round(co2_per_km, 1) if co2_per_km else None,
        'emission_factor': emission_factor,
        'fuel_type': fuel_type,
        'monthly_emissions': monthly_emissions,
        'eco_score': eco_score,
        'avg_efficiency': round(avg_efficiency, 2) if avg_efficiency else None,
        'benchmark_efficiency': benchmark,
        'trees_to_offset_yearly': round(trees_needed_yearly, 1),
        'carbon_offset_cost_usd': round(yearly_co2 * 0.02, 2),  # ~$20/ton average offset cost
    }
    
    # Fuel efficiency tips based on data
    fuel_tips = []
    if avg_efficiency:
        if avg_efficiency > benchmark * 1.2:
            fuel_tips.append({
                'id': 'high_consumption',
                'severity': 'warning',
                'title': 'Higher than average consumption',
                'description': f'Your average {avg_efficiency:.1f} L/100km is above the {benchmark:.1f} L/100km benchmark for {fuel_type} vehicles.',
                'actions': [
                    'Check tire pressure regularly',
                    'Remove excess weight from vehicle',
                    'Avoid aggressive acceleration',
                    'Use cruise control on highways'
                ]
            })
        elif avg_efficiency <= benchmark * 0.9:
            fuel_tips.append({
                'id': 'efficient_driving',
                'severity': 'success',
                'title': 'Excellent fuel efficiency!',
                'description': f'Your {avg_efficiency:.1f} L/100km beats the {benchmark:.1f} L/100km benchmark.',
                'actions': ['Keep up the eco-friendly driving habits!']
            })
    
    # Check for efficiency degradation  (fuel_top20 is capped at 20 rows)
    recent_entries = [e for e in fuel_top20[:5] if e.fuel_efficiency]
    older_entries = [e for e in fuel_top20[10:20] if e.fuel_efficiency]
    if len(recent_entries) >= 3 and len(older_entries) >= 3:
        recent_avg = weighted_efficiency(recent_entries)
        older_avg = weighted_efficiency(older_entries)
        if recent_avg is not None and older_avg is not None and recent_avg > older_avg * 1.15:
            fuel_tips.append({
                'id': 'efficiency_drop',
                'severity': 'warning',
                'title': 'Fuel efficiency has decreased',
                'description': f'Recent consumption ({recent_avg:.1f} L/100km) is higher than before ({older_avg:.1f} L/100km).',
                'actions': [
                    'Check air filter condition',
                    'Consider engine tune-up',
                    'Check for tire wear/alignment',
                    'Monitor driving patterns'
                ]
            })
    
    # ============================================
    # MAINTENANCE HEALTH
    # ============================================
    
    # Calculate days since last service
    last_service = service_entries[0] if service_entries else None
    days_since_service = None
    if last_service and last_service.date:
        days_since_service = (today - last_service.date).days
    
    # Calculate maintenance score (0-100)
    maintenance_score = 100
    maintenance_issues = []
    
    # Check service frequency
    past_services = [s for s in service_entries if s.date and s.date <= today]
    if len(past_services) >= 2:
        # Average days between services
        dates = sorted([s.date for s in past_services], reverse=True)
        intervals = [(dates[i] - dates[i+1]).days for i in range(len(dates)-1)]
        avg_interval = sum(intervals) / len(intervals) if intervals else 365
        
        if avg_interval > 365:
            maintenance_score -= 20
            maintenance_issues.append({
                'id': 'infrequent_service',
                'severity': 'warning',
                'title': 'Infrequent servicing',
                'description': f'Average {int(avg_interval)} days between services. Recommended: at least yearly.',
            })
    elif len(past_services) < 2 and vehicle.current_mileage and vehicle.current_mileage > 10000:
        maintenance_score -= 15
        maintenance_issues.append({
            'id': 'few_services',
            'severity': 'info',
            'title': 'Limited service history',
            'description': 'Consider documenting regular maintenance to maintain vehicle value.',
        })
    
    # Check if overdue for service
    if days_since_service and days_since_service > 365:
        maintenance_score -= 25
        maintenance_issues.append({
            'id': 'overdue_service',
            'severity': 'error',
            'title': 'Service overdue',
            'description': f'Last service was {days_since_service} days ago. Schedule maintenance soon.',
        })
    elif days_since_service and days_since_service > 270:
        maintenance_score -= 10
        maintenance_issues.append({
            'id': 'service_due_soon',
            'severity': 'warning',
            'title': 'Service due soon',
            'description': f'Last service was {days_since_service} days ago.',
        })
    
    # Check repair frequency — recent_repairs already bounded to last 6 months
    if len(recent_repairs) >= 3:
        maintenance_score -= 15
        maintenance_issues.append({
            'id': 'frequent_repairs',
            'severity': 'warning',
            'title': 'Frequent repairs detected',
            'description': f'{len(recent_repairs)} repairs in the last 6 months. Consider a comprehensive inspection.',
        })
    
    # ============================================
    # COMPONENT WEAR INDICATORS
    # ============================================
    
    # Estimate component status based on mileage and service history
    current_mileage = vehicle.current_mileage or 0

    # F31 — per-vehicle, unit-aware thresholds (defaults converted for miles
    # vehicles; user overrides overlaid). current_mileage is in the vehicle's
    # unit, so wear = distance_since / interval is now unit-consistent.
    effective_intervals = _effective_intervals(vehicle)
    vehicle_unit = vehicle.distance_unit or 'km'

    # Service keywords to detect
    SERVICE_KEYWORDS = {
        'oil_change': ['oil change', 'oil filter', 'motor oil', 'schimb ulei', 'cambio aceite'],
        'air_filter': ['air filter', 'filtru aer', 'filtro aire'],
        'cabin_filter': ['cabin filter', 'ac filter', 'hvac', 'filtru habitaclu', 'filtro habitáculo'],
        'brake_pads': ['brake pad', 'disc brake', 'frana', 'pastillas de freno'],
        'brake_fluid': ['brake fluid', 'lichid frana', 'líquido de frenos'],
        'transmission_fluid': ['transmission', 'gearbox', 'cutie viteze', 'transmisión'],
        'coolant': ['coolant', 'antifreeze', 'antigel', 'anticongelante'],
        'spark_plugs': ['spark plug', 'ignition', 'bujie', 'bujía'],
        'timing_belt': ['timing belt', 'timing chain', 'curea distributie', 'correa de distribución'],
        'tires': ['tire', 'tyre', 'wheel', 'anvelope', 'cauciuc', 'neumático'],
        'battery': ['battery', 'acumulator', 'baterie', 'batería'],
    }
    
    component_status = {}
    
    # Map repair types to component health keys
    REPAIR_TYPE_TO_COMPONENTS = {
        'engine': ['oil_change', 'spark_plugs'],
        'brakes': ['brake_pads', 'brake_fluid'],
        'cooling': ['coolant'],
        'tires_wheels': ['tires'],
        'electrical': ['battery'],
        'transmission': ['transmission_fluid'],
        'ac_heating': ['cabin_filter'],
        'oil_change': ['oil_change'],
        'filters': ['air_filter', 'cabin_filter'],
        'battery': ['battery'],
        'timing_belt': ['timing_belt'],
        'clutch': ['transmission_fluid'],
        'drivetrain': ['transmission_fluid'],
        'turbo': [],
        'differential': [],
        'windshield': [],
        'lights': [],
        'exhaust': [],
        'suspension': [],
        'steering': [],
        'fuel_system': [],
        'body': [],
        'interior': [],
        'other': [],
    }
    
    # Map service types to component health keys (for direct matching)
    SERVICE_TYPE_TO_COMPONENTS = {
        'oil_change': ['oil_change'],
        'tire_rotation': ['tires'],
        'brake_service': ['brake_pads', 'brake_fluid'],
        'air_filter': ['air_filter'],
        'cabin_filter': ['cabin_filter'],
        'spark_plugs': ['spark_plugs'],
        'transmission': ['transmission_fluid'],
        'coolant': ['coolant'],
        'timing_belt': ['timing_belt'],
        'inspection': [],
        'full_service': ['oil_change', 'air_filter', 'cabin_filter', 'brake_pads', 'brake_fluid',
                         'transmission_fluid', 'coolant', 'spark_plugs', 'tires', 'battery'],
        'other': [],
    }
    
    for component, interval in effective_intervals.items():
        keywords = SERVICE_KEYWORDS.get(component, [])
        
        # Find last service for this component
        last_service_date = None
        last_service_mileage = None
        for s in service_entries:
            # Direct match via service_types / service_type field
            s_types = s.service_types or ([s.service_type] if s.service_type else [])
            matched = False
            for stype in s_types:
                if component in SERVICE_TYPE_TO_COMPONENTS.get(stype, []):
                    matched = True
                    break
            
            # Keyword match on title/notes (fallback for legacy entries)
            if not matched:
                title_lower = (s.title or '').lower()
                notes_lower = (s.notes or '').lower()
                if any(kw in title_lower or kw in notes_lower for kw in keywords):
                    matched = True
            
            if matched:
                if last_service_date is None or (s.date and s.date > last_service_date):
                    last_service_date = s.date
                    last_service_mileage = s.odometer
        
        # Also check repair entries for matching repair types
        for r in repair_entries:
            r_types = r.repair_types or ([r.repair_type] if r.repair_type else [])
            for rtype in r_types:
                if component in REPAIR_TYPE_TO_COMPONENTS.get(rtype, []):
                    # Use this repair as evidence the component was serviced
                    if last_service_date is None or (r.date and r.date > last_service_date):
                        last_service_date = r.date
                        last_service_mileage = r.odometer
                    break
            # Also check repair description/notes for service keywords
            r_title = (r.title or '').lower()
            r_desc = (r.description or '').lower()
            r_notes = (r.notes or '').lower()
            combined = f'{r_title} {r_desc} {r_notes}'
            if any(kw in combined for kw in keywords):
                if last_service_date is None or (r.date and r.date > last_service_date):
                    last_service_date = r.date
                    last_service_mileage = r.odometer
        
        # Calculate wear percentage
        wear_pct = 0
        km_since_service = current_mileage - (last_service_mileage or 0) if last_service_mileage else current_mileage
        
        if km_since_service > 0:
            wear_pct = min(100, int((km_since_service / interval) * 100))
        
        # Determine status
        status = 'good'
        if wear_pct >= 100:
            status = 'overdue'
        elif wear_pct >= 80:
            status = 'due_soon'
        elif wear_pct >= 50:
            status = 'fair'
        
        component_status[component] = {
            'wear_percentage': wear_pct,
            'status': status,
            # F31 — values are in the vehicle's own unit; 'interval' replaces
            # the misleading 'interval_km' (kept as an alias for one release).
            'interval': interval,
            'interval_km': interval,
            'distance_unit': vehicle_unit,
            'km_since_last': km_since_service,
            'last_service_date': last_service_date.isoformat() if last_service_date else None,
            'last_service_mileage': last_service_mileage,
        }
    
    # ============================================
    # COST EFFICIENCY
    # ============================================
    
    # Calculate cost per km  (all-time totals from DB aggregates)
    total_costs = total_fuel_cost + total_service_cost + total_repair_cost
    
    cost_per_km = None
    if total_distance > 0:
        cost_per_km = total_costs / total_distance
    
    # Monthly cost trend — bounded to last 12 months
    monthly_costs = {}
    for e in fuel_year_entries:
        if e.date:
            key = e.date.strftime('%Y-%m')
            monthly_costs[key] = monthly_costs.get(key, 0) + float(e.total_price or 0)
    for e in service_entries:
        if e.date and e.date >= one_year_ago.date() and e.date <= today:
            key = e.date.strftime('%Y-%m')
            monthly_costs[key] = monthly_costs.get(key, 0) + float(e.amount or 0)
    for e in repair_entries:
        if e.date and e.date >= one_year_ago.date():
            key = e.date.strftime('%Y-%m')
            monthly_costs[key] = monthly_costs.get(key, 0) + float(e.amount or 0)
    
    # ============================================
    # OVERALL HEALTH SCORE
    # ============================================
    
    # Component health score
    overdue_components = sum(1 for c in component_status.values() if c['status'] == 'overdue')
    due_soon_components = sum(1 for c in component_status.values() if c['status'] == 'due_soon')
    component_health = max(0, 100 - (overdue_components * 15) - (due_soon_components * 5))
    
    # Calculate overall score
    overall_score = int(
        (maintenance_score * 0.35) +
        (component_health * 0.35) +
        (eco_score * 0.3)
    )
    
    # Determine health status
    if overall_score >= 80:
        health_status = 'excellent'
    elif overall_score >= 60:
        health_status = 'good'
    elif overall_score >= 40:
        health_status = 'fair'
    else:
        health_status = 'needs_attention'
    
    # ============================================
    # VEHICLE AGE & WARRANTY
    # ============================================
    
    vehicle_age_years = None
    if vehicle.year:
        vehicle_age_years = current_year - vehicle.year
    
    # F2: real warranty ledger from stored dates/mileage, replacing the previous
    # age-based guess. 'active' when ≥1 item is still under warranty, else 'none'.
    _wsummary = warranty_summary(vehicle)
    warranty_count = _wsummary['count']
    warranty_nearest_days_left = _wsummary['nearest_days_left']
    warranty_status = 'active' if warranty_count > 0 else 'none'
    
    # ============================================
    # RECOMMENDED ACTIONS (Prioritized)
    # ============================================
    
    recommended_actions = []
    
    # High priority - overdue components
    for comp, data in component_status.items():
        if data['status'] == 'overdue':
            recommended_actions.append({
                'priority': 'high',
                'type': 'maintenance',
                'component': comp,
                'title': f'{comp.replace("_", " ").title()} - Overdue',
                'description': (f'Last done {data["km_since_last"]:,} {vehicle_unit} ago. '
                                f'Recommended interval: {data["interval"]:,} {vehicle_unit}.'),
            })
    
    # Medium priority - due soon
    for comp, data in component_status.items():
        if data['status'] == 'due_soon':
            recommended_actions.append({
                'priority': 'medium',
                'type': 'maintenance',
                'component': comp,
                'title': f'{comp.replace("_", " ").title()} - Due Soon',
                'description': f'At {data["wear_percentage"]}% of maintenance interval.',
            })
    
    # Add maintenance issues
    for issue in maintenance_issues:
        if issue['severity'] == 'error':
            recommended_actions.append({
                'priority': 'high',
                'type': 'service',
                'title': issue['title'],
                'description': issue['description'],
            })
        elif issue['severity'] == 'warning':
            recommended_actions.append({
                'priority': 'medium',
                'type': 'service',
                'title': issue['title'],
                'description': issue['description'],
            })
    
    # Carbon offset recommendation if significant emissions
    if yearly_co2 > 1000:  # More than 1 ton/year
        recommended_actions.append({
            'priority': 'low',
            'type': 'environment',
            'title': 'Consider carbon offset',
            'description': f'Your annual emissions of {yearly_co2:.0f} kg CO2 could be offset for ~${yearly_co2 * 0.02:.2f}.',
        })
    
    # Sort by priority
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    recommended_actions.sort(key=lambda x: priority_order.get(x['priority'], 3))

    # F30 — persist the computed scores on the Vehicle row so the garage list
    # and to_dict(include_stats=True) return real values with zero extra
    # computation. View-driven refresh; a write failure must NEVER break the
    # health read.
    try:
        vehicle.maintenance_score = maintenance_score
        vehicle.cost_per_km = round(cost_per_km, 4) if cost_per_km else None
        vehicle.avg_fuel_efficiency = avg_efficiency
        vehicle.health_score = overall_score
        vehicle.health_computed_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning(f'Health-score persist failed (read unaffected): {e}')

    return jsonify({
        'vehicle_id': vehicle_id,
        'vehicle_name': vehicle.name,
        'overall_score': overall_score,
        'health_status': health_status,
        'scores': {
            'maintenance': maintenance_score,
            'components': component_health,
            'eco_driving': eco_score,
        },
        'carbon_footprint': carbon_footprint,
        'fuel_tips': fuel_tips,
        'maintenance': {
            'score': maintenance_score,
            'last_service_date': last_service.date.isoformat() if last_service and last_service.date else None,
            'days_since_service': days_since_service,
            'total_services': len([s for s in service_entries if s.date and s.date <= today]),
            'total_repairs': len(repair_entries),
            'issues': maintenance_issues,
        },
        'components': component_status,
        'cost_efficiency': {
            'total_costs': round(total_costs, 2),
            'total_distance_km': total_distance,
            'distance_unit': vehicle.distance_unit or 'km',
            'cost_per_km': round(cost_per_km, 3) if cost_per_km else None,
            'monthly_costs': monthly_costs,
        },
        'vehicle_info': {
            'age_years': vehicle_age_years,
            'current_mileage': current_mileage,
            'fuel_type': fuel_type,
            'warranty_status': warranty_status,
            'warranty_count': warranty_count,
            'warranty_nearest_days_left': warranty_nearest_days_left,
            'distance_unit': vehicle.distance_unit or 'km',
        },
        'recommended_actions': recommended_actions[:10],  # Top 10
    })


@vehicles_bp.route('/<int:vehicle_id>/warranties', methods=['GET'])
@token_required
def get_vehicle_warranties(current_user, vehicle_id):
    """Warranty ledger (F2): every service/repair/consumable still under warranty.

    Computed from the warranty data already captured on each entry (explicit
    expiry date, or entry date + warranty_months, and/or warranty_km against the
    vehicle's current mileage). Only in-force items are returned, soonest expiry
    first. Ownership is enforced by scoping to the caller's vehicle.
    """
    vehicle = Vehicle.query.filter_by(id=vehicle_id, user_id=current_user.id).first()
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404

    items = build_vehicle_warranties(vehicle)
    days = [i['days_left'] for i in items if i['days_left'] is not None]
    return jsonify({
        'items': items,
        'count': len(items),
        'nearest_days_left': min(days) if days else None,
        'distance_unit': vehicle.distance_unit or 'km',
    })


@vehicles_bp.route('/<int:vehicle_id>/health/actions/complete', methods=['POST'])
@token_required
def complete_health_action(current_user, vehicle_id):
    """Log a recommended maintenance action as a service entry (Mark Done).

    Creates a real ServiceEntry so the health endpoint naturally recalculates
    component status and clears the completed item from Recommended Actions.
    Mileage is optional — when provided it is stored as the odometer reading
    and, if higher than the vehicle's current mileage, updates it.
    """
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404

    data = request.get_json(silent=True) or {}

    # --- component validation -------------------------------------------
    # Only accept known component keys — title is sourced from our own lookup,
    # never from user input (prevents arbitrary string injection into ServiceEntry.title).
    _COMPONENT_MAP = {
        # component            service_type       human title
        'oil_change':         ('oil_change',       'Oil Change'),
        'air_filter':         ('air_filter',        'Air Filter'),
        'cabin_filter':       ('cabin_filter',      'Cabin Filter'),
        'brake_pads':         ('brake_service',     'Brake Pads'),
        'brake_fluid':        ('brake_service',     'Brake Fluid'),
        'tires':              ('tire_rotation',     'Tire Rotation'),
        'spark_plugs':        ('spark_plugs',       'Spark Plugs'),
        'timing_belt':        ('timing_belt',       'Timing Belt'),
        'battery':            ('other',             'Battery'),
        'transmission_fluid': ('transmission',      'Transmission Fluid'),
        'coolant':            ('coolant',           'Coolant'),
        'general_service':    ('other',             'Service'),
    }

    component_raw = data.get('component', '')
    if not isinstance(component_raw, str) or not component_raw.strip():
        return jsonify({'error': 'component is required'}), 400

    component = component_raw.strip().lower()

    if component not in _COMPONENT_MAP:
        return jsonify({'error': 'Invalid component'}), 400

    service_type, title = _COMPONENT_MAP[component]

    # --- optional mileage -----------------------------------------------
    # Cap at 9_999_999 to stay safely within DB INTEGER range (prevents overflow)
    _MILEAGE_MAX = 9_999_999
    odometer = None
    mileage_raw = data.get('mileage')
    if mileage_raw is not None:
        try:
            odometer = int(mileage_raw)
            if odometer < 0 or odometer > _MILEAGE_MAX:
                odometer = None
        except (ValueError, TypeError):
            odometer = None

    # --- optional notes (sanitised) -------------------------------------
    notes_raw = data.get('notes', '')
    notes = str(notes_raw).strip()[:500] if notes_raw else None

    today = datetime.now(timezone.utc).date()

    entry = ServiceEntry(
        user_id=current_user.id,
        vehicle_id=vehicle_id,
        title=title,
        service_type=service_type,
        service_types=[service_type],
        date=today,
        odometer=odometer,
        amount=0,
        currency=current_user.chosen_currency,
        notes=notes,
    )
    db.session.add(entry)

    # Update vehicle mileage only when new reading is higher (never decrement)
    if odometer is not None and (vehicle.current_mileage is None or odometer > vehicle.current_mileage):
        vehicle.current_mileage = odometer

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.error(
            'Failed to log health action for vehicle %s', vehicle_id, exc_info=True
        )
        return jsonify({'error': 'Failed to record service. Please try again later.'}), 500

    return jsonify({'success': True, 'service_entry_id': entry.id}), 201


@vehicles_bp.route('/<int:vehicle_id>/manual', methods=['GET'])
@token_required
def get_vehicle_manual(current_user, vehicle_id):
    """
    Resolve the owner's manual URL for a specific vehicle.

    Reads make/model/year from the vehicle's DB record and the user's
    language preference. Nothing is hardcoded — every lookup is fully dynamic.
    """
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id,
    ).first()

    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404

    if not vehicle.make or not vehicle.model or not vehicle.year:
        return jsonify({
            'error': 'Vehicle make, model, and year are required for manual lookup',
            'manual_url': None,
            'source': None,
            'fallback_search': None,
        }), 400

    lang = getattr(current_user, 'language', None) or 'en'

    from app.services.manual_service import get_manual_url
    result = get_manual_url(
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        lang=lang,
    )

    return jsonify({
        **result,
        'make': vehicle.make,
        'model': vehicle.model,
        'year': vehicle.year,
        'language': lang,
    })
