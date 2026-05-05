"""
GearCargo - Vehicles Routes
"""

import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func

from app import db
from app.models import Vehicle, Entry, FuelEntry, ServiceEntry, RepairEntry
from app.models.attachment import Attachment
from app.routes.auth import token_required

vehicles_bp = Blueprint('vehicles', __name__)


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


@vehicles_bp.route('/<int:vehicle_id>/archive', methods=['POST'])
@token_required
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

    vehicle.archived = True
    vehicle.archived_at = datetime.now(timezone.utc)

    # Cancel all active insurance policies for this vehicle
    try:
        from app.models import InsurancePolicy
        active_policies = InsurancePolicy.query.filter(
            InsurancePolicy.vehicle_id == vehicle_id,
            InsurancePolicy.status == 'active'
        ).all()
        for policy in active_policies:
            policy.status = 'cancelled'
            policy.end_date = datetime.now(timezone.utc).date()
            policy.auto_renew = False
    except Exception as e:
        current_app.logger.warning(f'Failed to cancel insurance policies on archive: {e}')

    # Cancel all recurring tax entries for this vehicle
    try:
        from app.models import TaxEntry
        recurring_taxes = TaxEntry.query.filter(
            TaxEntry.vehicle_id == vehicle_id,
            TaxEntry.recurring == True
        ).all()
        for tax in recurring_taxes:
            tax.recurring = False
            tax.next_due_date = None
    except Exception as e:
        current_app.logger.warning(f'Failed to cancel recurring taxes on archive: {e}')

    db.session.commit()

    return jsonify({
        'message': 'Vehicle archived successfully',
        'vehicle': vehicle.to_dict()
    })


@vehicles_bp.route('/<int:vehicle_id>/unarchive', methods=['POST'])
@token_required
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
    db.session.commit()
    
    return jsonify({
        'message': 'Vehicle restored successfully',
        'vehicle': vehicle.to_dict()
    })


@vehicles_bp.route('', methods=['POST'])
@token_required
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
        engine_cc=data.get('engine_cc'),
        transmission=data.get('transmission'),
        drivetrain=data.get('drivetrain'),
        current_mileage=data.get('current_mileage', 0),
        distance_unit=data.get('distance_unit', 'km'),
        purchase_date=datetime.fromisoformat(data['purchase_date']).date() if data.get('purchase_date') else None,
        purchase_price=data.get('purchase_price'),
        monthly_budget=data.get('monthly_budget'),
    )
    
    db.session.add(vehicle)
    db.session.commit()
    
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
    
    return jsonify(vehicle.to_dict(include_stats=True))


@vehicles_bp.route('/<int:vehicle_id>', methods=['PUT'])
@token_required
def update_vehicle(current_user, vehicle_id):
    """Update a vehicle."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    data = request.get_json()
    
    # Update allowed fields
    allowed = ['name', 'make', 'model', 'year', 'vin', 'license_plate',
               'color', 'fuel_type', 'engine_cc', 'transmission',
               'drive_type', 'body_type', 'current_mileage', 'notes',
               'is_active', 'photo_url', 'distance_unit', 'tank_capacity',
               'vehicle_height_cm', 'vehicle_width_cm', 'vehicle_weight_kg']
    
    for field in allowed:
        if field in data:
            if field == 'current_mileage':
                # Allow correcting mileage, but not below highest recorded entry
                max_recorded = _get_max_recorded_odometer(current_user.id, vehicle_id)
                if data[field] < max_recorded:
                    return jsonify({
                        'error': f'Mileage cannot be lower than the highest recorded entry ({max_recorded})',
                        'message_key': 'vehicles.mileageBelowRecordedMax',
                        'min_allowed_mileage': max_recorded,
                    }), 400
            setattr(vehicle, field, data[field])
    
    db.session.commit()
    
    return jsonify({
        'message': 'Vehicle updated',
        'vehicle': vehicle.to_dict()
    })


@vehicles_bp.route('/<int:vehicle_id>', methods=['DELETE'])
@token_required
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
        # Delete physical attachment files
        attachments = Attachment.query.filter_by(vehicle_id=vehicle_id).all()
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        for att in attachments:
            if att.filepath:
                file_path = os.path.join(upload_folder, att.filepath) if not os.path.isabs(att.filepath) else att.filepath
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except OSError:
                    pass
        # Cascade delete via SQLAlchemy relationships
        db.session.delete(vehicle)
    else:
        vehicle.is_active = False
    
    db.session.commit()
    
    return jsonify({'message': 'Vehicle deleted'})


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
        vehicle = Vehicle.query.get(vehicle_id)
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
    
    from datetime import datetime
    from sqlalchemy import func, extract

    # Current date info
    now = datetime.now(timezone.utc)
    today = now.date()  # Convert to date for comparison with entry dates
    current_year = now.year
    current_month = now.month

    # ------------------------------------------------------------------
    # FUEL — DB-level aggregates; zero rows fetched into Python memory
    # ------------------------------------------------------------------
    total_fuel_cost = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.total_price), 0))
        .filter(FuelEntry.vehicle_id == vehicle_id)
        .scalar()
    )
    ytd_fuel_cost = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.total_price), 0))
        .filter(
            FuelEntry.vehicle_id == vehicle_id,
            extract('year', FuelEntry.date) == current_year,
        )
        .scalar()
    )
    fuel_month_cost = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.total_price), 0))
        .filter(
            FuelEntry.vehicle_id == vehicle_id,
            extract('year', FuelEntry.date) == current_year,
            extract('month', FuelEntry.date) == current_month,
        )
        .scalar()
    )
    fuel_count = int(
        db.session.query(func.count(FuelEntry.id))
        .filter(FuelEntry.vehicle_id == vehicle_id)
        .scalar() or 0
    )

    # ------------------------------------------------------------------
    # SERVICE — aggregate for totals/counts; past-only (date <= today)
    # ------------------------------------------------------------------
    total_service_cost = float(
        db.session.query(func.coalesce(func.sum(ServiceEntry.amount), 0))
        .filter(ServiceEntry.vehicle_id == vehicle_id, ServiceEntry.date <= today)
        .scalar()
    )
    service_count = int(
        db.session.query(func.count(ServiceEntry.id))
        .filter(ServiceEntry.vehicle_id == vehicle_id, ServiceEntry.date <= today)
        .scalar() or 0
    )
    service_month_cost = float(
        db.session.query(func.coalesce(func.sum(ServiceEntry.amount), 0))
        .filter(
            ServiceEntry.vehicle_id == vehicle_id,
            ServiceEntry.date <= today,
            extract('year', ServiceEntry.date) == current_year,
            extract('month', ServiceEntry.date) == current_month,
        )
        .scalar()
    )
    service_ytd_cost = float(
        db.session.query(func.coalesce(func.sum(ServiceEntry.amount), 0))
        .filter(
            ServiceEntry.vehicle_id == vehicle_id,
            ServiceEntry.date <= today,
            extract('year', ServiceEntry.date) == current_year,
        )
        .scalar()
    )

    # ------------------------------------------------------------------
    # REPAIR — DB-level aggregates
    # ------------------------------------------------------------------
    total_repair_cost = float(
        db.session.query(func.coalesce(func.sum(RepairEntry.amount), 0))
        .filter(RepairEntry.vehicle_id == vehicle_id)
        .scalar()
    )
    repair_count = int(
        db.session.query(func.count(RepairEntry.id))
        .filter(RepairEntry.vehicle_id == vehicle_id)
        .scalar() or 0
    )
    repair_month_cost = float(
        db.session.query(func.coalesce(func.sum(RepairEntry.amount), 0))
        .filter(
            RepairEntry.vehicle_id == vehicle_id,
            extract('year', RepairEntry.date) == current_year,
            extract('month', RepairEntry.date) == current_month,
        )
        .scalar()
    )
    repair_ytd_cost = float(
        db.session.query(func.coalesce(func.sum(RepairEntry.amount), 0))
        .filter(
            RepairEntry.vehicle_id == vehicle_id,
            extract('year', RepairEntry.date) == current_year,
        )
        .scalar()
    )

    # ------------------------------------------------------------------
    # PARKING — DB-level aggregates (model may not exist on all installs)
    # ------------------------------------------------------------------
    parking_costs = 0.0
    parking_month_cost = 0.0
    parking_ytd_cost = 0.0
    try:
        from app.models.parking import ParkingEntry
        parking_costs = float(
            db.session.query(func.coalesce(func.sum(ParkingEntry.amount), 0))
            .filter(ParkingEntry.vehicle_id == vehicle_id)
            .scalar()
        )
        parking_month_cost = float(
            db.session.query(func.coalesce(func.sum(ParkingEntry.amount), 0))
            .filter(
                ParkingEntry.vehicle_id == vehicle_id,
                extract('year', ParkingEntry.date) == current_year,
                extract('month', ParkingEntry.date) == current_month,
            )
            .scalar()
        )
        parking_ytd_cost = float(
            db.session.query(func.coalesce(func.sum(ParkingEntry.amount), 0))
            .filter(
                ParkingEntry.vehicle_id == vehicle_id,
                extract('year', ParkingEntry.date) == current_year,
            )
            .scalar()
        )
    except Exception:
        pass

    # ------------------------------------------------------------------
    # TAX — DB-level aggregates
    # ------------------------------------------------------------------
    tax_costs = 0.0
    ytd_tax_costs = 0.0
    tax_month_cost = 0.0
    try:
        from app.models.tax import TaxEntry
        tax_costs = float(
            db.session.query(func.coalesce(func.sum(TaxEntry.amount), 0))
            .filter(TaxEntry.vehicle_id == vehicle_id)
            .scalar()
        )
        ytd_tax_costs = float(
            db.session.query(func.coalesce(func.sum(TaxEntry.amount), 0))
            .filter(
                TaxEntry.vehicle_id == vehicle_id,
                extract('year', TaxEntry.date) == current_year,
            )
            .scalar()
        )
        tax_month_cost = float(
            db.session.query(func.coalesce(func.sum(TaxEntry.amount), 0))
            .filter(
                TaxEntry.vehicle_id == vehicle_id,
                extract('year', TaxEntry.date) == current_year,
                extract('month', TaxEntry.date) == current_month,
            )
            .scalar()
        )
    except Exception:
        pass

    # ------------------------------------------------------------------
    # INSURANCE — bounded .all() (always < ~20 policies per vehicle).
    # Complex frequency-based logic cannot be expressed in simple SQL.
    # ------------------------------------------------------------------
    insurance_policies = []
    insurance_annual_cost = 0.0
    try:
        from app.models.insurance import InsurancePolicy
        insurance_policies = InsurancePolicy.query.filter_by(vehicle_id=vehicle_id).all()
        for policy in insurance_policies:
            premium = float(policy.premium or 0)
            frequency = policy.payment_frequency or 'annual'
            if frequency == 'monthly':
                insurance_annual_cost += premium * 12
            elif frequency == 'quarterly':
                insurance_annual_cost += premium * 4
            elif frequency in ('semi-annual', 'semi_annual'):
                insurance_annual_cost += premium * 2
            else:  # annual/yearly/one_time
                insurance_annual_cost += premium
    except Exception:
        pass

    # ------------------------------------------------------------------
    # DERIVED TOTALS (no iteration needed — all from DB scalars above)
    # ------------------------------------------------------------------
    total_costs = (
        total_fuel_cost + total_service_cost + total_repair_cost
        + parking_costs + tax_costs + insurance_annual_cost
    )

    # --- This month's costs ---
    monthly_insurance_cost = 0.0
    costs_this_month = (
        fuel_month_cost + service_month_cost + repair_month_cost
        + parking_month_cost + tax_month_cost
    )
    for policy in insurance_policies:
        if not policy.start_date:
            continue
        policy_started = (
            policy.start_date.year < current_year
            or (policy.start_date.year == current_year and policy.start_date.month <= current_month)
        )
        policy_ended = policy.end_date and (
            policy.end_date.year < current_year
            or (policy.end_date.year == current_year and policy.end_date.month < current_month)
        )
        if not policy_started or policy_ended:
            continue
        premium = float(policy.premium or 0)
        frequency = policy.payment_frequency or 'annual'
        if frequency == 'monthly':
            payment_day = policy.start_date.day
            if today.day >= payment_day:
                monthly_insurance_cost += premium
                costs_this_month += premium
        elif frequency == 'quarterly':
            start_month = policy.start_date.month
            months_diff = (current_year - policy.start_date.year) * 12 + (current_month - start_month)
            if months_diff >= 0 and months_diff % 3 == 0:
                monthly_insurance_cost += premium
                costs_this_month += premium
        elif frequency in ('semi-annual', 'semi_annual'):
            start_month = policy.start_date.month
            months_diff = (current_year - policy.start_date.year) * 12 + (current_month - start_month)
            if months_diff >= 0 and months_diff % 6 == 0:
                monthly_insurance_cost += premium
                costs_this_month += premium
        elif frequency in ('annual', 'yearly', 'one_time'):
            if policy.start_date.year == current_year and policy.start_date.month == current_month:
                monthly_insurance_cost += premium
                costs_this_month += premium

    # --- YTD costs ---
    ytd_insurance_costs = 0.0
    for policy in insurance_policies:
        if not policy.start_date:
            continue
        premium = float(policy.premium or 0)
        frequency = policy.payment_frequency or 'annual'
        if frequency == 'monthly':
            payment_day = policy.start_date.day
            paid_through_month = current_month if today.day >= payment_day else current_month - 1
            start_month = max(1, policy.start_date.month) if policy.start_date.year == current_year else 1
            end_month = paid_through_month
            if policy.end_date and policy.end_date.year == current_year:
                end_month = min(end_month, policy.end_date.month)
            if policy.start_date.year <= current_year and (not policy.end_date or policy.end_date.year >= current_year):
                ytd_insurance_costs += premium * max(0, end_month - start_month + 1)
        elif frequency == 'quarterly':
            if policy.start_date.year <= current_year:
                start_month = policy.start_date.month
                payments = sum(
                    1 for q in range(4)
                    if (start_month + q * 3) <= 12
                    and (start_month + q * 3) <= current_month
                    and (not policy.end_date or policy.end_date >= today)
                )
                ytd_insurance_costs += premium * payments
        elif frequency in ('semi-annual', 'semi_annual'):
            if policy.start_date.year <= current_year:
                start_month = policy.start_date.month
                payments = sum(
                    1 for s in range(2)
                    if (start_month + s * 6) <= 12
                    and (start_month + s * 6) <= current_month
                    and (not policy.end_date or policy.end_date >= today)
                )
                ytd_insurance_costs += premium * payments
        elif frequency in ('annual', 'yearly', 'one_time'):
            if policy.start_date.year == current_year and policy.start_date.month <= current_month:
                ytd_insurance_costs += premium

    ytd_spent = (
        ytd_fuel_cost + service_ytd_cost + repair_ytd_cost
        + parking_ytd_cost + ytd_tax_costs + ytd_insurance_costs
    )

    # ------------------------------------------------------------------
    # AVERAGE FUEL CONSUMPTION (L/100km)
    # Attempt 1: DB AVG of stored efficiency values (no rows fetched).
    # Fallback to capped queries only if the stored column is empty.
    # ------------------------------------------------------------------
    avg_consumption = None
    _avg_eff = (
        db.session.query(func.avg(FuelEntry.fuel_efficiency))
        .filter(
            FuelEntry.vehicle_id == vehicle_id,
            FuelEntry.fuel_efficiency.isnot(None),
        )
        .scalar()
    )
    if _avg_eff is not None:
        avg_consumption = float(_avg_eff)

    if avg_consumption is None:
        # Fallback: trip_distance + liters (capped at 500 rows)
        valid_trips = (
            db.session.query(FuelEntry.liters, FuelEntry.trip_distance)
            .filter(
                FuelEntry.vehicle_id == vehicle_id,
                FuelEntry.liters.isnot(None),
                FuelEntry.trip_distance.isnot(None),
                FuelEntry.trip_distance > 0,
            )
            .limit(500)
            .all()
        )
        if valid_trips:
            avg_consumption = sum(float(l) / float(d) * 100 for l, d in valid_trips) / len(valid_trips)

    if avg_consumption is None:
        # Fallback: consecutive odometer readings (capped at 500 rows)
        sorted_fuel = (
            db.session.query(FuelEntry.liters, FuelEntry.odometer)
            .filter(
                FuelEntry.vehicle_id == vehicle_id,
                FuelEntry.odometer.isnot(None),
                FuelEntry.liters.isnot(None),
            )
            .order_by(FuelEntry.odometer.asc())
            .limit(500)
            .all()
        )
        calc = []
        for i in range(1, len(sorted_fuel)):
            dist = float(sorted_fuel[i].odometer) - float(sorted_fuel[i - 1].odometer)
            if dist > 0:
                calc.append(float(sorted_fuel[i].liters) / dist * 100)
        if calc:
            avg_consumption = sum(calc) / len(calc)
    
    # Next service due - check both reminders AND future service entries
    next_service = None
    next_service_title = None
    next_service_days = None
    
    try:
        # First check reminders
        from app.models.reminder import Reminder
        upcoming_reminder = Reminder.query.filter_by(
            vehicle_id=vehicle_id,
            completed=False,
            dismissed=False
        ).filter(
            Reminder.due_date >= now
        ).order_by(Reminder.due_date.asc()).first()
        
        if upcoming_reminder:
            next_service = upcoming_reminder.due_date.strftime('%Y-%m-%d')
            next_service_title = upcoming_reminder.title
            next_service_days = (upcoming_reminder.due_date - now).days
    except Exception:
        pass
    
    # Also check for future service entries (scheduled services with date in the future)
    try:
        future_service = ServiceEntry.query.filter(
            ServiceEntry.vehicle_id == vehicle_id,
            ServiceEntry.date >= now
        ).order_by(ServiceEntry.date.asc()).first()
        
        if future_service:
            service_date = future_service.date
            # Use the earlier of reminder or scheduled service
            if not next_service or service_date < datetime.strptime(next_service, '%Y-%m-%d').date():
                next_service = service_date.strftime('%Y-%m-%d')
                next_service_title = future_service.title or future_service.service_type or 'Scheduled Service'
                next_service_days = (service_date - now).days
    except Exception:
        pass
    
    # Also check for service entries with next_due_date set (past services with next service scheduled)
    try:
        service_with_next_due = ServiceEntry.query.filter(
            ServiceEntry.vehicle_id == vehicle_id,
            ServiceEntry.next_due_date.isnot(None),
            ServiceEntry.next_due_date >= now
        ).order_by(ServiceEntry.next_due_date.asc()).first()
        
        if service_with_next_due:
            due_date = service_with_next_due.next_due_date
            # Use the earlier of existing next_service or this due date
            if not next_service or due_date < datetime.strptime(next_service, '%Y-%m-%d').date():
                next_service = due_date.strftime('%Y-%m-%d')
                next_service_title = f"Next {service_with_next_due.title or service_with_next_due.service_type or 'Service'}"
                next_service_days = (due_date - now).days
    except Exception:
        pass
    
    return jsonify({
        'vehicle_id': vehicle_id,
        'total_costs': float(total_costs),
        'ytd_spent': float(ytd_spent),
        'costs_this_month': float(costs_this_month),
        'monthly_insurance_cost': float(monthly_insurance_cost),  # Insurance cost for this month only
        'fuel_costs': float(total_fuel_cost),
        'ytd_fuel_costs': float(ytd_fuel_cost),
        'service_costs': float(total_service_cost),
        'repair_costs': float(total_repair_cost),
        'parking_costs': float(parking_costs),
        'tax_costs': float(ytd_tax_costs),  # YTD tax expenses
        'insurance_costs': float(ytd_insurance_costs),  # YTD insurance paid
        'insurance_annual_cost': float(insurance_annual_cost),  # Annualized insurance cost
        'service_count': service_count,
        'repair_count': repair_count,
        'fuel_count': fuel_count,
        'insurance_count': len(insurance_policies),
        'avg_consumption': float(avg_consumption) if avg_consumption else None,
        'next_service': next_service,
        'next_service_title': next_service_title,
        'next_service_days': next_service_days,
    })


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
        'parking', 'reminder', 'todo', 'insurance',
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
                    if frequency == 'monthly':
                        annual_cost = premium * 12
                    elif frequency == 'quarterly':
                        annual_cost = premium * 4
                    elif frequency in ('semi-annual', 'semi_annual'):
                        annual_cost = premium * 2
                    else:
                        annual_cost = premium
                    insurance_items.append({
                        'id':               policy.id,
                        'type':             'insurance',
                        'title':            policy.provider,
                        'description':      f"{policy.provider} - {policy.policy_number or 'Policy'}",
                        'amount':           premium,
                        'cost':             premium,
                        'annual_cost':      annual_cost,
                        'payment_frequency': frequency,
                        'date':             policy.start_date.isoformat() if policy.start_date else None,
                        'vehicle_id':       policy.vehicle_id,
                        'created_at':       policy.created_at.isoformat() if policy.created_at else None,
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

    else:
        eq = Entry.query.filter_by(vehicle_id=vehicle_id)
        if entry_type != 'all':
            eq = eq.filter(Entry.type == entry_type)

        entry_total = eq.count()

        # On page 1 we merge insurance records into the entry window.
        # Fetch a slightly larger buffer so insurance doesn't displace entries
        # that the user expects to see on this page.
        buffer   = len(insurance_items)          # > 0 only on page 1
        db_limit = per_page + buffer

        # For pages after page 1: adjust the DB offset so we don't skip the
        # entries that were "consumed" by insurance records on page 1.
        if page == 1:
            db_offset = 0
        else:
            # insurance_total records appeared before (or within) page 1;
            # shift the offset back so those entries aren't silently skipped.
            db_offset = max(0, (page - 1) * per_page - insurance_total)

        entries_raw = (
            eq
            .order_by(Entry.date.desc(), Entry.id.desc())
            .offset(db_offset)
            .limit(db_limit)
            .all()
        )
        entry_items = [e.to_dict(include_attachments=False) for e in entries_raw]

        # In-memory merge is at most (per_page + ~20) items — no OOM risk.
        merged = entry_items + insurance_items
        merged.sort(key=lambda x: x.get('date') or '', reverse=True)
        result_items = merged[:per_page]

        total = entry_total + insurance_total

    pages = max(1, (total + per_page - 1) // per_page)

    return jsonify({
        'entries':      result_items,
        'total':        total,
        'pages':        pages,
        'current_page': page,
        'per_page':     per_page,
        'has_next':     page < pages,
        'has_prev':     page > 1,
    })


@vehicles_bp.route('/<int:vehicle_id>/mileage', methods=['POST'])
@token_required
def update_mileage(current_user, vehicle_id):
    """Update vehicle mileage."""
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    data = request.get_json()
    new_mileage = data.get('mileage')
    
    if not new_mileage:
        return jsonify({'error': 'Mileage is required'}), 400
    
    max_recorded_odometer = _get_max_recorded_odometer(current_user.id, vehicle.id)
    if new_mileage < max_recorded_odometer:
        return jsonify({
            'error': f'Mileage cannot be lower than the highest recorded entry ({max_recorded_odometer})',
            'message_key': 'vehicles.mileageBelowRecordedMax',
            'min_allowed_mileage': max_recorded_odometer,
        }), 400
    
    vehicle.current_mileage = new_mileage
    db.session.commit()
    
    return jsonify({
        'message': 'Mileage updated',
        'message_key': 'vehicles.mileageUpdated',
        'current_mileage': vehicle.current_mileage
    })


@vehicles_bp.route('/summary', methods=['GET'])
@token_required
def get_vehicles_summary(current_user):
    """Get summary of all vehicles."""
    vehicles = Vehicle.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()
    
    total_cost = 0
    total_fuel = 0
    
    for vehicle in vehicles:
        # Quick sum of costs
        fuel_cost = db.session.query(func.sum(FuelEntry.total_price)).filter_by(
            vehicle_id=vehicle.id
        ).scalar() or 0
        
        service_cost = db.session.query(func.sum(ServiceEntry.amount)).filter_by(
            vehicle_id=vehicle.id
        ).scalar() or 0
        
        repair_cost = db.session.query(func.sum(RepairEntry.amount)).filter_by(
            vehicle_id=vehicle.id
        ).scalar() or 0
        
        total_cost += fuel_cost + service_cost + repair_cost
        
        total_fuel += db.session.query(func.sum(FuelEntry.liters)).filter_by(
            vehicle_id=vehicle.id
        ).scalar() or 0
    
    return jsonify({
        'vehicle_count': len(vehicles),
        'total_cost': float(total_cost),
        'total_fuel_volume': float(total_fuel),
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
    _avg_eff_raw = (
        db.session.query(func.avg(FuelEntry.fuel_efficiency))
        .filter(
            FuelEntry.vehicle_id == vehicle_id,
            FuelEntry.fuel_efficiency.isnot(None),
            FuelEntry.fuel_efficiency > 0,
        )
        .scalar()
    )
    avg_efficiency = float(_avg_eff_raw) if _avg_eff_raw is not None else None

    total_distance = float(
        db.session.query(func.coalesce(func.sum(FuelEntry.trip_distance), 0))
        .filter(
            FuelEntry.vehicle_id == vehicle_id,
            FuelEntry.trip_distance.isnot(None),
        )
        .scalar()
    )
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
        recent_avg = sum(e.fuel_efficiency for e in recent_entries) / len(recent_entries)
        older_avg = sum(e.fuel_efficiency for e in older_entries) / len(older_entries)
        if recent_avg > older_avg * 1.15:
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
    
    # Standard maintenance intervals (km)
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
    
    for component, interval in MAINTENANCE_INTERVALS.items():
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
            'interval_km': interval,
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
    
    warranty_status = 'unknown'
    warranty_tips = []
    if vehicle_age_years:
        if vehicle_age_years <= 3:
            warranty_status = 'likely_covered'
            warranty_tips.append('Your vehicle may still be under manufacturer warranty.')
        elif vehicle_age_years <= 5:
            warranty_status = 'extended_possible'
            warranty_tips.append('Consider extended warranty options if not already purchased.')
        else:
            warranty_status = 'likely_expired'
            warranty_tips.append('Standard warranty likely expired. Focus on preventive maintenance.')
    
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
                'description': f'Last done {data["km_since_last"]:,} km ago. Recommended interval: {data["interval_km"]:,} km.',
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
            'cost_per_km': round(cost_per_km, 3) if cost_per_km else None,
            'monthly_costs': monthly_costs,
        },
        'vehicle_info': {
            'age_years': vehicle_age_years,
            'current_mileage': current_mileage,
            'fuel_type': fuel_type,
            'warranty_status': warranty_status,
            'warranty_tips': warranty_tips,
            'distance_unit': vehicle.distance_unit or 'km',
        },
        'recommended_actions': recommended_actions[:10],  # Top 10
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
        currency=current_user.currency or 'EUR',
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
