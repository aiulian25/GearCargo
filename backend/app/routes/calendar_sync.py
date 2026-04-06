"""
GearCargo - Calendar Sync Routes
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from icalendar import Calendar, Event
from io import BytesIO
from sqlalchemy import and_, or_

from app import db
from app.models import (
    Reminder, Vehicle, FuelEntry, ServiceEntry, RepairEntry,
    TaxEntry, ParkingEntry, InsurancePolicy, Todo
)
from app.routes.auth import token_required

calendar_bp = Blueprint('calendar', __name__)


@calendar_bp.route('/entries', methods=['GET'])
@token_required
def get_calendar_entries(current_user):
    """Get all entries for the calendar view."""
    # Get query parameters
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    # Parse dates
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            # Default to start of current month
            today = datetime.utcnow()
            start_date = today.replace(day=1).date()
        
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            # Default to end of current month + next month
            today = datetime.utcnow()
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=2, day=1).date() - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 2, day=1).date() - timedelta(days=1)
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    entries = []
    
    # Get all vehicles for this user (for vehicle name lookup)
    vehicles_dict = {}
    vehicles_query = Vehicle.query.filter_by(user_id=current_user.id, archived=False)
    for v in vehicles_query.all():
        vehicles_dict[v.id] = v.name
    
    # Base filter for vehicle
    def vehicle_filter(model):
        base = model.user_id == current_user.id
        if vehicle_id:
            return and_(base, model.vehicle_id == vehicle_id)
        return base
    
    # 1. Fuel entries
    fuel_entries = FuelEntry.query.filter(
        vehicle_filter(FuelEntry),
        FuelEntry.date >= start_date,
        FuelEntry.date <= end_date
    ).all()
    
    for entry in fuel_entries:
        total_cost = float(entry.total_price) if entry.total_price else (float(entry.amount) if entry.amount else 0)
        liters_val = float(entry.liters) if entry.liters else 0
        entries.append({
            'id': f'fuel-{entry.id}',
            'type': 'fuel',
            'date': entry.date.isoformat(),
            'title': f'{liters_val:.1f}L - {total_cost:.2f}',
            'vehicle_id': entry.vehicle_id,
            'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown'),
            'cost': total_cost,
            'details': {
                'liters': liters_val,
                'price_per_liter': float(entry.price_per_liter) if entry.price_per_liter else 0,
                'mileage': entry.odometer,
                'fuel_type': entry.fuel_type,
                'station': entry.station
            }
        })
    
    # 2. Service entries
    service_entries = ServiceEntry.query.filter(
        vehicle_filter(ServiceEntry),
        ServiceEntry.date >= start_date,
        ServiceEntry.date <= end_date
    ).all()
    
    for entry in service_entries:
        total_cost = float(entry.amount) if entry.amount else 0
        entries.append({
            'id': f'service-{entry.id}',
            'type': 'service',
            'date': entry.date.isoformat(),
            'title': entry.service_type or 'Service',
            'vehicle_id': entry.vehicle_id,
            'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown'),
            'cost': total_cost,
            'details': {
                'service_type': entry.service_type,
                'description': entry.description,
                'shop_name': entry.garage_name,
                'mileage': entry.odometer
            }
        })
    
    # 3. Repair entries
    repair_entries = RepairEntry.query.filter(
        vehicle_filter(RepairEntry),
        RepairEntry.date >= start_date,
        RepairEntry.date <= end_date
    ).all()
    
    for entry in repair_entries:
        total_cost = float(entry.amount) if entry.amount else 0
        entries.append({
            'id': f'repair-{entry.id}',
            'type': 'repair',
            'date': entry.date.isoformat(),
            'title': entry.repair_type or entry.description or 'Repair',
            'vehicle_id': entry.vehicle_id,
            'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown'),
            'cost': total_cost,
            'details': {
                'repair_type': entry.repair_type,
                'description': entry.description,
                'shop_name': entry.garage_name,
                'mileage': entry.odometer
            }
        })
    
    # 4. Tax entries - use date field instead of payment_date
    tax_entries = TaxEntry.query.filter(
        vehicle_filter(TaxEntry),
        TaxEntry.date >= start_date,
        TaxEntry.date <= end_date
    ).all()
    
    for entry in tax_entries:
        entries.append({
            'id': f'tax-{entry.id}',
            'type': 'tax',
            'date': entry.date.isoformat(),
            'title': entry.tax_type or 'Tax',
            'vehicle_id': entry.vehicle_id,
            'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown'),
            'cost': float(entry.amount) if entry.amount else 0,
            'details': {
                'tax_type': entry.tax_type,
                'due_date': entry.due_date.isoformat() if entry.due_date else None,
                'paid_date': entry.paid_date.isoformat() if entry.paid_date else None,
                'reference_number': entry.reference_number
            }
        })
    
    # 5. Parking entries
    parking_entries = ParkingEntry.query.filter(
        vehicle_filter(ParkingEntry),
        ParkingEntry.date >= start_date,
        ParkingEntry.date <= end_date
    ).all()
    
    for entry in parking_entries:
        entries.append({
            'id': f'parking-{entry.id}',
            'type': 'parking',
            'date': entry.date.isoformat(),
            'title': entry.location or entry.parking_type or 'Parking',
            'vehicle_id': entry.vehicle_id,
            'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown'),
            'cost': float(entry.amount) if entry.amount else 0,
            'details': {
                'parking_type': entry.parking_type,
                'location': entry.location,
                'start_time': entry.start_datetime.isoformat() if entry.start_datetime else None,
                'end_time': entry.end_datetime.isoformat() if entry.end_datetime else None
            }
        })
    
    # 6. Insurance policies (show start date and end date as separate entries)
    insurance_policies = InsurancePolicy.query.filter(
        vehicle_filter(InsurancePolicy),
        or_(
            and_(InsurancePolicy.start_date >= start_date, InsurancePolicy.start_date <= end_date),
            and_(InsurancePolicy.end_date >= start_date, InsurancePolicy.end_date <= end_date)
        )
    ).all()
    
    for entry in insurance_policies:
        # Add start date entry
        if entry.start_date and start_date <= entry.start_date <= end_date:
            entries.append({
                'id': f'insurance-start-{entry.id}',
                'type': 'insurance',
                'subtype': 'start',
                'date': entry.start_date.isoformat(),
                'title': f'{entry.policy_type or "Insurance"} Start',
                'vehicle_id': entry.vehicle_id,
                'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown'),
                'cost': float(entry.premium) if entry.premium else 0,
                'details': {
                    'insurance_type': entry.policy_type,
                    'provider': entry.provider,
                    'policy_number': entry.policy_number,
                    'premium': float(entry.premium) if entry.premium else 0
                }
            })
        
        # Add end date entry (expiry)
        if entry.end_date and start_date <= entry.end_date <= end_date:
            entries.append({
                'id': f'insurance-end-{entry.id}',
                'type': 'insurance',
                'subtype': 'end',
                'date': entry.end_date.isoformat(),
                'title': f'{entry.policy_type or "Insurance"} Expiry',
                'vehicle_id': entry.vehicle_id,
                'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown'),
                'cost': 0,
                'details': {
                    'insurance_type': entry.policy_type,
                    'provider': entry.provider,
                    'policy_number': entry.policy_number
                }
            })
    
    # 7. Reminders (due dates)
    reminders = Reminder.query.filter(
        Reminder.user_id == current_user.id,
        Reminder.due_date >= start_date,
        Reminder.due_date <= end_date
    )
    if vehicle_id:
        reminders = reminders.filter(Reminder.vehicle_id == vehicle_id)
    reminders = reminders.all()
    
    for entry in reminders:
        # Determine status from completed/dismissed fields
        if entry.completed:
            status = 'completed'
        elif entry.dismissed:
            status = 'dismissed'
        elif entry.is_overdue:
            status = 'overdue'
        else:
            status = 'pending'
        
        entries.append({
            'id': f'reminder-{entry.id}',
            'type': 'reminder',
            'date': entry.due_date.isoformat(),
            'title': entry.title,
            'vehicle_id': entry.vehicle_id,
            'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown') if entry.vehicle_id else None,
            'cost': 0,
            'status': status,
            'priority': entry.priority,
            'details': {
                'reminder_type': entry.reminder_type,
                'description': entry.description,
                'due_mileage': entry.due_mileage,
                'status': status
            }
        })
    
    # 8. Todos (due dates)
    todos = Todo.query.filter(
        Todo.user_id == current_user.id,
        Todo.due_date.isnot(None),
        Todo.due_date >= start_date,
        Todo.due_date <= end_date
    )
    if vehicle_id:
        todos = todos.filter(Todo.vehicle_id == vehicle_id)
    todos = todos.all()
    
    for entry in todos:
        entries.append({
            'id': f'todo-{entry.id}',
            'type': 'todo',
            'date': entry.due_date.isoformat(),
            'title': entry.title,
            'vehicle_id': entry.vehicle_id,
            'vehicle_name': vehicles_dict.get(entry.vehicle_id, 'Unknown') if entry.vehicle_id else None,
            'cost': 0,
            'status': 'completed' if entry.completed else 'pending',
            'priority': entry.priority,
            'details': {
                'description': entry.description,
                'completed': entry.completed
            }
        })
    
    # Sort entries by date
    entries.sort(key=lambda x: x['date'])
    
    return jsonify({
        'entries': entries,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'total_count': len(entries)
    })


@calendar_bp.route('/export', methods=['GET'])
@token_required
def export_calendar(current_user):
    """Export reminders to iCal format."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//GearCargo//Vehicle Management//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', 'GearCargo Reminders')
    
    # Query reminders
    query = Reminder.query.filter(
        Reminder.user_id == current_user.id,
        Reminder.status == 'pending',
        Reminder.due_date.isnot(None)
    )
    
    if vehicle_id:
        query = query.filter(Reminder.vehicle_id == vehicle_id)
    
    reminders = query.all()
    
    for reminder in reminders:
        event = Event()
        
        # Get vehicle info
        vehicle_name = ''
        if reminder.vehicle_id:
            vehicle = Vehicle.query.get(reminder.vehicle_id)
            if vehicle:
                vehicle_name = f" - {vehicle.name}"
        
        event.add('uid', f'reminder-{reminder.id}@gearcargo')
        event.add('summary', f'{reminder.title}{vehicle_name}')
        event.add('description', reminder.description or '')
        event.add('dtstart', reminder.due_date)
        event.add('dtend', reminder.due_date)
        
        # Add priority
        if reminder.priority == 'high':
            event.add('priority', 1)
        elif reminder.priority == 'low':
            event.add('priority', 9)
        else:
            event.add('priority', 5)
        
        # Add alarm/reminder
        from icalendar import Alarm
        alarm = Alarm()
        alarm.add('action', 'DISPLAY')
        alarm.add('trigger', timedelta(days=-1))
        alarm.add('description', f'Reminder: {reminder.title}')
        event.add_component(alarm)
        
        event.add('created', reminder.created_at or datetime.utcnow())
        event.add('dtstamp', datetime.utcnow())
        
        cal.add_component(event)
    
    # Return iCal file
    buffer = BytesIO()
    buffer.write(cal.to_ical())
    buffer.seek(0)
    
    from flask import send_file
    return send_file(
        buffer,
        mimetype='text/calendar',
        as_attachment=True,
        download_name='gearcargo_reminders.ics'
    )


@calendar_bp.route('/feed/<token>', methods=['GET'])
def calendar_feed(token):
    """Public calendar feed URL (for calendar subscriptions)."""
    from app.models import User
    import jwt
    
    try:
        # Verify token
        payload = jwt.decode(
            token,
            current_app.config['JWT_SECRET_KEY'],
            algorithms=['HS256']
        )
        
        if payload.get('type') != 'calendar_feed':
            return jsonify({'error': 'Invalid token'}), 401
        
        user = User.query.get(payload['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401
    
    # Create calendar
    cal = Calendar()
    cal.add('prodid', '-//GearCargo//Vehicle Management//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', 'GearCargo Reminders')
    cal.add('x-wr-timezone', user.timezone or 'UTC')
    
    # Get reminders
    reminders = Reminder.query.filter(
        Reminder.user_id == user.id,
        Reminder.calendar_sync == True,
        Reminder.completed == False,
        Reminder.due_date.isnot(None)
    ).all()
    
    for reminder in reminders:
        event = Event()
        
        vehicle_name = ''
        if reminder.vehicle_id:
            vehicle = Vehicle.query.get(reminder.vehicle_id)
            if vehicle:
                vehicle_name = f" - {vehicle.name}"
        
        event.add('uid', f'reminder-{reminder.id}@gearcargo')
        event.add('summary', f'{reminder.title}{vehicle_name}')
        event.add('description', reminder.description or '')
        event.add('dtstart', reminder.due_date)
        event.add('dtend', reminder.due_date)
        event.add('created', reminder.created_at or datetime.utcnow())
        event.add('dtstamp', datetime.utcnow())
        
        cal.add_component(event)
    
    from flask import Response
    return Response(
        cal.to_ical(),
        mimetype='text/calendar',
        headers={'Content-Disposition': 'inline; filename=gearcargo.ics'}
    )


@calendar_bp.route('/feed-token', methods=['POST'])
@token_required
def generate_feed_token(current_user):
    """Generate a calendar feed token."""
    import jwt
    
    token = jwt.encode(
        {
            'user_id': current_user.id,
            'type': 'calendar_feed',
            'created': datetime.utcnow().isoformat(),
            'exp': datetime.utcnow() + timedelta(days=90)
        },
        current_app.config['JWT_SECRET_KEY'],
        algorithm='HS256'
    )
    
    feed_url = f"{request.host_url}api/calendar/feed/{token}"
    
    return jsonify({
        'token': token,
        'feed_url': feed_url,
        'message': 'Use this URL to subscribe to your calendar'
    })


@calendar_bp.route('/sync-status', methods=['GET'])
@token_required
def get_sync_status(current_user):
    """Get calendar sync status for reminders."""
    synced = Reminder.query.filter(
        Reminder.user_id == current_user.id,
        Reminder.calendar_sync == True
    ).count()
    
    total = Reminder.query.filter(
        Reminder.user_id == current_user.id,
        Reminder.completed == False
    ).count()
    
    return jsonify({
        'synced_reminders': synced,
        'total_pending': total,
    })


@calendar_bp.route('/sync-all', methods=['POST'])
@token_required
def sync_all_reminders(current_user):
    """Enable calendar sync for all pending reminders."""
    updated = Reminder.query.filter(
        Reminder.user_id == current_user.id,
        Reminder.completed == False,
        Reminder.due_date.isnot(None)
    ).update({'calendar_sync': True})
    
    db.session.commit()
    
    return jsonify({
        'message': f'Enabled calendar sync for {updated} reminders',
        'updated': updated
    })


# ============================================================
# CALENDAR CONFIGURATION ENDPOINTS
# ============================================================

@calendar_bp.route('/providers', methods=['GET'])
@token_required
def get_calendar_providers(current_user):
    """Get list of supported calendar providers."""
    from app.services.calendar_service import CALENDAR_PROVIDERS
    
    providers = []
    for provider_id, provider_info in CALENDAR_PROVIDERS.items():
        providers.append({
            'id': provider_id,
            'name': provider_info['name'],
            'requires_oauth': provider_info.get('requires_oauth', False),
            'help_url': provider_info.get('help_url', ''),
            'default_url': provider_info.get('caldav_url', ''),
            'setup_guide_key': f'settings.calendarSetupGuide.{provider_id}'
        })
    
    return jsonify({'providers': providers})


@calendar_bp.route('/settings', methods=['GET'])
@token_required
def get_calendar_settings(current_user):
    """Get user's calendar sync settings."""
    from app.services.calendar_service import get_user_calendar_sources

    sources = get_user_calendar_sources(current_user)
    primary = next((s for s in sources if s.get('enabled')), None) or (sources[0] if sources else None)

    return jsonify({
        'enabled': current_user.calendar_enabled or False,
        'provider': primary.get('provider') if primary else current_user.calendar_provider,
        'url': primary.get('url') if primary else current_user.calendar_url,
        'username': primary.get('username') if primary else current_user.calendar_username,
        'calendar_id': primary.get('calendar_id') if primary else current_user.calendar_id,
        'configured': bool(primary and primary.get('provider') and primary.get('url') and primary.get('username')),
        'sources': sources,
        'last_sync': current_user.calendar_last_sync.isoformat() if current_user.calendar_last_sync else None,
    })


@calendar_bp.route('/settings', methods=['POST', 'PUT'])
@token_required
def update_calendar_settings(current_user):
    """Update user's calendar sync settings."""
    from app.services.calendar_service import (
        build_caldav_url,
        build_source_for_storage,
        get_user_calendar_sources,
        set_user_calendar_sources,
        validate_calendar_source,
    )
    
    # Use silent=True to handle missing Content-Type header gracefully
    data = request.get_json(silent=True) or {}
    
    existing_sources = get_user_calendar_sources(current_user, include_secrets=True)
    existing_by_id = {source.get('id'): source for source in existing_sources}

    payload_sources = data.get('sources')
    if payload_sources is None:
        # Legacy payload compatibility: map single source fields into a list.
        provider = data.get('provider', current_user.calendar_provider)
        username = data.get('username', current_user.calendar_username)
        server = (data.get('server') or '').strip()
        url = data.get('url', current_user.calendar_url)
        if server:
            url = build_caldav_url(provider, server, username or '', data.get('email', current_user.email) or '')

        payload_sources = [{
            'id': (existing_sources[0]['id'] if existing_sources else 'source_primary'),
            'name': data.get('name') or provider or 'caldav',
            'provider': provider,
            'url': url,
            'username': username,
            'password': data.get('password', ''),
            'calendar_id': data.get('calendar_id', current_user.calendar_id),
            'enabled': data.get('enabled', current_user.calendar_enabled),
        }]

    if not isinstance(payload_sources, list):
        return jsonify({'error': 'Invalid calendar sources', 'message_key': 'calendar.sources.invalid_format'}), 400

    if len(payload_sources) > 10:
        return jsonify({'error': 'Too many calendar sources', 'message_key': 'calendar.sources.limit_exceeded'}), 400

    new_sources = []
    seen_ids = set()

    for raw_source in payload_sources:
        if not isinstance(raw_source, dict):
            return jsonify({'error': 'Invalid calendar source item', 'message_key': 'calendar.source.invalid_format'}), 400

        source_id = str(raw_source.get('id') or '').strip()
        existing_source = existing_by_id.get(source_id)

        source_payload = dict(raw_source)
        source_payload['id'] = source_id or (existing_source.get('id') if existing_source else None)

        if source_payload.get('server') and source_payload.get('provider') and source_payload.get('provider') != 'caldav':
            source_payload['url'] = build_caldav_url(
                source_payload.get('provider'),
                str(source_payload.get('server')).strip(),
                source_payload.get('username') or '',
                data.get('email', current_user.email) or ''
            )

        source_to_store = build_source_for_storage(source_payload, existing_source)

        if source_to_store['id'] in seen_ids:
            return jsonify({'error': 'Duplicate calendar source id', 'message_key': 'calendar.source.duplicate_id'}), 400
        seen_ids.add(source_to_store['id'])

        validation_error = validate_calendar_source(source_to_store)
        if validation_error:
            return jsonify({'error': 'Invalid calendar source', 'message_key': validation_error, 'source_id': source_to_store['id']}), 400

        if source_to_store.get('enabled') and not source_to_store.get('password'):
            return jsonify({'error': 'Missing password for enabled source', 'message_key': 'calendar.source.password_required', 'source_id': source_to_store['id']}), 400

        new_sources.append(source_to_store)

    set_user_calendar_sources(current_user, new_sources)
    if 'enabled' in data:
        current_user.calendar_enabled = bool(data.get('enabled'))
    
    db.session.commit()
    
    safe_sources = get_user_calendar_sources(current_user)
    primary = next((s for s in safe_sources if s.get('enabled')), None) or (safe_sources[0] if safe_sources else None)

    return jsonify({
        'message_key': 'calendar.settings.updated',
        'message': 'Calendar settings updated',
        'enabled': current_user.calendar_enabled,
        'provider': primary.get('provider') if primary else None,
        'url': primary.get('url') if primary else None,
        'username': primary.get('username') if primary else None,
        'calendar_id': primary.get('calendar_id') if primary else None,
        'configured': bool(primary and primary.get('provider') and primary.get('url') and primary.get('username')),
        'sources': safe_sources,
    })


@calendar_bp.route('/test', methods=['POST'])
@token_required
def test_calendar_connection(current_user):
    """Test calendar connection with current settings."""
    from app.services.calendar_service import (
        CalendarService,
        build_source_for_storage,
        get_user_calendar_sources,
        validate_calendar_source,
    )
    
    # Check if temporary credentials provided in request
    # Use silent=True to handle missing Content-Type header gracefully
    data = request.get_json(silent=True) or {}
    
    source = None
    existing_sources = get_user_calendar_sources(current_user, include_secrets=True)

    if data.get('source_id'):
        source = next((item for item in existing_sources if item.get('id') == data.get('source_id')), None)
        if not source:
            return jsonify({'error': 'Source not found', 'message_key': 'calendar.source.not_found'}), 404

    if data.get('source'):
        raw_source = data.get('source')
        if not isinstance(raw_source, dict):
            return jsonify({'error': 'Invalid source', 'message_key': 'calendar.source.invalid_format'}), 400
        source = build_source_for_storage(raw_source, source)

    if not source:
        source = next((item for item in existing_sources if item.get('enabled')), None) or (existing_sources[0] if existing_sources else None)

    if not source:
        return jsonify({'success': False, 'message_key': 'calendar.source.not_configured', 'message': 'Calendar source is not configured', 'calendars': []}), 400

    validation_error = validate_calendar_source(source)
    if validation_error:
        return jsonify({'success': False, 'message_key': validation_error, 'message': 'Invalid source configuration', 'calendars': []}), 400

    if not source.get('password'):
        return jsonify({'success': False, 'message_key': 'calendar.source.password_required', 'message': 'Missing password for calendar source', 'calendars': []}), 400

    service = CalendarService(current_user, source)
    success, message = service.connect()

    calendars = []
    if success:
        calendars = service.get_calendars()

    return jsonify({
        'success': success,
        'message_key': 'calendar.connection.success' if success else 'calendar.connection.failed',
        'message': message,
        'calendars': calendars,
        'source_id': source.get('id'),
    })


@calendar_bp.route('/calendars', methods=['GET'])
@token_required
def get_available_calendars(current_user):
    """Get list of available calendars from the connected account."""
    from app.services.calendar_service import CalendarService, get_user_calendar_sources

    source_id = request.args.get('source_id')
    sources = get_user_calendar_sources(current_user, include_secrets=True)
    if source_id:
        source = next((item for item in sources if item.get('id') == source_id), None)
    else:
        source = next((item for item in sources if item.get('enabled')), None) or (sources[0] if sources else None)

    if not source:
        return jsonify({'error': 'Source not found', 'message_key': 'calendar.source.not_found', 'calendars': []}), 404

    service = CalendarService(current_user, source)
    success, message = service.connect()
    
    if not success:
        return jsonify({'error': message, 'message_key': 'calendar.connection.failed', 'calendars': []}), 400
    
    calendars = service.get_calendars()
    return jsonify({'calendars': calendars, 'source_id': source.get('id')})


@calendar_bp.route('/sync', methods=['POST'])
@token_required
def sync_all_entries(current_user):
    """Manually sync all entries to calendar."""
    from app.services.calendar_service import sync_all_entries_for_user
    
    if not current_user.calendar_enabled:
        return jsonify({'error': 'Calendar sync is disabled', 'message_key': 'calendar.sync.disabled'}), 400
    
    results = sync_all_entries_for_user(current_user)
    
    # Update last sync time
    current_user.calendar_last_sync = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'message_key': 'calendar.sync.summary',
        'message': f'Synced {results["synced"]} entries, {results["failed"]} failed',
        'synced': results['synced'],
        'failed': results['failed'],
        'errors': results['errors'][:5] if results['errors'] else []  # Only return first 5 errors
    })


@calendar_bp.route('/sync/entry', methods=['POST'])
@token_required
def sync_single_entry(current_user):
    """Sync a single entry to calendar."""
    from app.services.calendar_service import sync_entry_to_calendar
    from app.models import ServiceEntry, RepairEntry, InsurancePolicy, TaxEntry
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'No data provided', 'message_key': 'calendar.sync.invalid_payload'}), 400
    
    entry_type = data.get('type')
    entry_id = data.get('id')
    action = data.get('action', 'create')
    
    if not entry_type or not entry_id:
        return jsonify({'error': 'Missing type or id', 'message_key': 'calendar.sync.missing_type_or_id'}), 400
    
    # Get the entry based on type
    entry = None
    if entry_type == 'service':
        entry = ServiceEntry.query.filter_by(id=entry_id, user_id=current_user.id).first()
    elif entry_type == 'repair':
        entry = RepairEntry.query.filter_by(id=entry_id, user_id=current_user.id).first()
    elif entry_type == 'reminder':
        entry = Reminder.query.filter_by(id=entry_id, user_id=current_user.id).first()
    elif entry_type == 'insurance':
        entry = InsurancePolicy.query.join(Vehicle).filter(
            InsurancePolicy.id == entry_id,
            Vehicle.user_id == current_user.id
        ).first()
    elif entry_type == 'tax':
        entry = TaxEntry.query.filter_by(id=entry_id, user_id=current_user.id).first()
    
    if not entry:
        return jsonify({'error': 'Entry not found', 'message_key': 'calendar.sync.entry_not_found'}), 404
    
    success, message = sync_entry_to_calendar(current_user, entry_type, entry, action)
    
    return jsonify({
        'success': success,
        'message': message,
        'message_key': 'calendar.sync.entry_success' if success else 'calendar.sync.entry_failed'
    })

