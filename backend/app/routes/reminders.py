"""
GearCargo - Reminders Routes
"""

from app.services.vehicle_archive import active_vehicle_condition
from app.services.mutations import mutation_endpoint, commit_mutation

from datetime import datetime, date, timedelta, timezone
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import func, case, and_

from app import db
from app.models import Vehicle, Reminder
from app.routes.auth import token_required
from app.utils.entryparse import (
    REQUIRED_FIELD_KEY,
    InvalidFieldError,
    invalid_field_response,
    parse_iso_date,
    parse_optional_int,
)
from app.utils.timeutils import utc_today

reminders_bp = Blueprint('reminders', __name__)

# UI "Repeats" values (AddVehicleReminder.jsx) ↔ (frequency, frequency_value).
_REPEAT_INTERVALS = {
    '1_week': ('weekly', 1),
    '1_month': ('monthly', 1),
    '3_months': ('monthly', 3),
    '6_months': ('monthly', 6),
    '1_year': ('yearly', 1),
    '2_years': ('yearly', 2),
    # The standalone AddReminder form uses these equivalent tokens.
    'weekly': ('weekly', 1),
    'monthly': ('monthly', 1),
    'quarterly': ('monthly', 3),
    'biannually': ('monthly', 6),
    'yearly': ('yearly', 1),
}


# Integer columns, by the request key that addresses them. Kept apart from the
# string/bool aliases below because every one of them needs coercing before it
# reaches the column (R4-11). Canonical name last, so it wins when both are sent.
_INTEGER_FIELDS = {
    'due_mileage': 'due_mileage',
    'repeat_mileage': 'repeat_mileage',
    'notify_days_before': 'notify_days_before',
    'recurrence_interval': 'frequency_value',
    'frequency_value': 'frequency_value',
}


def _apply_repeat_interval(reminder, raw):
    """Apply the form's repeat_interval value onto the recurrence columns."""
    if raw:
        mapped = _REPEAT_INTERVALS.get(raw)
        if mapped:
            reminder.recurring = True
            reminder.frequency, reminder.frequency_value = mapped
    else:  # '' / null → does not repeat
        reminder.recurring = False
        reminder.frequency = None
        reminder.frequency_value = None


@reminders_bp.route('', methods=['GET'])
@token_required
def get_reminders(current_user):
    """Get reminders."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    status = request.args.get('status')  # upcoming, overdue, completed, pending, snoozed
    page = request.args.get('page', 1, type=int)
    per_page = max(1, min(request.args.get('per_page', 20, type=int), 100))
    
    query = Reminder.query.filter_by(user_id=current_user.id)
    if status in ('upcoming', 'overdue', 'pending', 'snoozed'):
        query = query.filter(active_vehicle_condition(Reminder))
    
    if vehicle_id:
        query = query.filter(Reminder.vehicle_id == vehicle_id)
    
    today = utc_today()
    
    if status:
        if status == 'upcoming':
            # Not completed, not dismissed, due date is today or in the future
            query = query.filter(
                Reminder.completed == False,
                Reminder.dismissed == False,
                db.or_(
                    Reminder.due_date >= today,
                    Reminder.due_date.is_(None)
                )
            )
        elif status == 'overdue':
            # Not completed, not dismissed, due date is in the past
            query = query.filter(
                Reminder.completed == False,
                Reminder.dismissed == False,
                Reminder.due_date < today
            )
        elif status == 'pending':
            query = query.filter(Reminder.completed == False, Reminder.dismissed == False)
        elif status == 'completed':
            query = query.filter(Reminder.completed == True)
        elif status == 'snoozed':
            query = query.filter(Reminder.snoozed_until.isnot(None))
        elif status == 'dismissed':
            query = query.filter(Reminder.dismissed == True)
    
    reminders = query.order_by(Reminder.due_date.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'reminders': [r.to_dict() for r in reminders.items],
        'total': reminders.total,
        'pages': reminders.pages,
        'current_page': page,
    })


@reminders_bp.route('', methods=['POST'])
@token_required
@mutation_endpoint(Reminder)
def create_reminder(current_user):
    """Create a new reminder."""
    data = request.get_json()
    
    # Validate vehicle if provided
    vehicle_id = data.get('vehicle_id')
    if vehicle_id:
        vehicle = Vehicle.query.filter_by(
            id=vehicle_id,
            user_id=current_user.id
        ).first()
        if not vehicle:
            return jsonify({'error': 'Vehicle not found'}), 404
    
    if not data.get('title'):
        return jsonify({'error': 'Title is required',
                        'message_key': REQUIRED_FIELD_KEY}), 400

    # due_date is NOT NULL (models/reminder.py:22) — omitting it used to reach
    # the flush as an IntegrityError 500.
    if not data.get('due_date'):
        return jsonify({'error': 'Due date is required',
                        'message_key': REQUIRED_FIELD_KEY}), 400

    # Every parse below raises InvalidFieldError, caught once — malformed input
    # used to escape as a 500 (R4-10) or reach an Integer column raw (R4-11).
    try:
        due_date = parse_iso_date(data['due_date'])
        due_mileage = parse_optional_int(data.get('due_mileage'),
                                         'Due mileage must be a number')
        notify_days_before = parse_optional_int(data.get('notify_days_before', 7),
                                                'Notification days must be a number')
        frequency_value = parse_optional_int(data.get('recurrence_interval'),
                                             'Repeat interval must be a number')
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    reminder = Reminder(
        user_id=current_user.id,
        vehicle_id=vehicle_id,
        title=data['title'],
        description=data.get('description'),
        reminder_type=data.get('reminder_type', 'custom'),
        due_date=due_date,
        due_mileage=due_mileage,
        repeat_mileage=data.get('repeat_mileage'),
        priority=data.get('priority', 'medium'),
        completed=False,
        dismissed=False,
        # Recurrence
        recurring=data.get('is_recurring', False),
        frequency=data.get('recurrence_pattern'),
        frequency_value=frequency_value,
        # Notifications
        notify_days_before=notify_days_before,
        notify_push=data.get('notify_push', data.get('notify_via_push', True)),
        notify_email=data.get('notify_email', data.get('notify_via_email', True)),
        # Calendar
        calendar_sync=data.get('sync_to_calendar', False),
        # Translations
        title_translations=data.get('title_translations'),
        description_translations=data.get('description_translations'),
    )

    # The reminder form sends 'notes' and 'repeat_interval' — map them to the
    # real columns (F18).
    if data.get('notes') and not data.get('description'):
        reminder.description = data['notes']
    if 'repeat_interval' in data:
        _apply_repeat_interval(reminder, data['repeat_interval'])

    if reminder.repeat_mileage is not None and (not reminder.recurring or not reminder.frequency or reminder.due_mileage is None):
        return jsonify({'error': 'Choose a repeat interval and a due mileage before setting a mileage interval.',
                        'message_key': 'reminderDelivery.intervalRequired'}), 400
    if reminder.recurring:
        reminder.recurrence_anchor_date = reminder.due_date
    db.session.add(reminder)
    commit_mutation()
    
    # Auto-sync to calendar if enabled
    if current_user.calendar_enabled:
        try:
            from app.services.calendar_service import sync_entry_to_calendar
            sync_entry_to_calendar(current_user, 'reminder', reminder, 'create')
        except Exception as e:
            current_app.logger.warning(f"Calendar sync failed for reminder: {e}")
    
    return jsonify({
        'message': 'Reminder created',
        'reminder': reminder.to_dict()
    }), 201


@reminders_bp.route('/<int:reminder_id>', methods=['GET'])
@token_required
def get_reminder(current_user, reminder_id):
    """Get a specific reminder."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    return jsonify(reminder.to_dict())


@reminders_bp.route('/<int:reminder_id>', methods=['PUT'])
@token_required
@mutation_endpoint(Reminder, 'reminder_id')
def update_reminder(current_user, reminder_id):
    """Update a reminder."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    data = request.get_json()
    
    old_schedule = (reminder.due_date, reminder.due_mileage)

    # F18 — request keys mapped to the REAL model columns. Aliases first,
    # canonical names last so the canonical value wins when both are sent.
    # ('status' and 'recurrence_unit' were dropped — no such columns; the
    # integer columns live in _INTEGER_FIELDS, they cannot be assigned raw.)
    field_aliases = {
        'title': 'title',
        'notes': 'description', 'description': 'description',
        'reminder_type': 'reminder_type',
        'priority': 'priority',
        'is_recurring': 'recurring', 'recurring': 'recurring',
        'recurrence_pattern': 'frequency', 'frequency': 'frequency',
        'notify_via_push': 'notify_push', 'notify_push': 'notify_push',
        'notify_via_email': 'notify_email', 'notify_email': 'notify_email',
        'sync_to_calendar': 'calendar_sync', 'calendar_sync': 'calendar_sync',
        'title_translations': 'title_translations',
        'description_translations': 'description_translations',
    }

    # Parsed up front so a rejected field cannot leave the earlier ones already
    # applied — the loop below used to mutate the reminder as it went (R4-11).
    try:
        parsed_columns = {}
        # A falsy due_date stays a no-op, as before: the column is NOT NULL, and
        # the edit form sends '' to mean "unchanged".
        if data.get('due_date'):
            parsed_columns['due_date'] = parse_iso_date(data['due_date'])
        for key, column in _INTEGER_FIELDS.items():
            if key in data:
                parsed_columns[column] = parse_optional_int(data[key])
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status

    for key, column in field_aliases.items():
        if key in data:
            setattr(reminder, column, data[key])

    for column, value in parsed_columns.items():
        setattr(reminder, column, value)

    # The reminder form's "Repeats" select (F18) — applied last so it wins
    # over any alias-provided recurrence fields.
    if 'repeat_interval' in data:
        _apply_repeat_interval(reminder, data['repeat_interval'])
    
    if reminder.repeat_mileage is not None and (not reminder.recurring or not reminder.frequency or reminder.due_mileage is None):
        return jsonify({'error': 'Choose a repeat interval and a due mileage before setting a mileage interval.',
                        'message_key': 'reminderDelivery.intervalRequired'}), 400
    if old_schedule != (reminder.due_date, reminder.due_mileage):
        reminder.notification_state = {}
        reminder.last_notified_at = None
        reminder.mileage_notified = False
    if reminder.recurring and (old_schedule[0] != reminder.due_date or not reminder.recurrence_anchor_date):
        reminder.recurrence_anchor_date = reminder.due_date

    commit_mutation()
    
    return jsonify({
        'message': 'Reminder updated',
        'reminder': reminder.to_dict()
    })


@reminders_bp.route('/<int:reminder_id>', methods=['DELETE'])
@token_required
@mutation_endpoint(Reminder, 'reminder_id')
def delete_reminder(current_user, reminder_id):
    """Delete a reminder."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    db.session.delete(reminder)
    commit_mutation()
    
    return jsonify({'message': 'Reminder deleted'})


@reminders_bp.route('/<int:reminder_id>/complete', methods=['POST'])
@token_required
@mutation_endpoint(Reminder, 'reminder_id')
def complete_reminder(current_user, reminder_id):
    """Mark reminder as completed."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404

    if not reminder.completed and reminder.recurring and reminder.vehicle and reminder.vehicle.archived:
        return jsonify({'error': 'Restore the vehicle before completing a recurring task.', 'code': 'VEHICLE_ARCHIVED'}), 409

    if reminder.completed:
        return jsonify({'message': 'Reminder completed', 'reminder': reminder.to_dict()})
    next_due_date = None
    next_due_mileage = None
    if reminder.recurring and reminder.frequency:
        from app.services.reminder_recurrence import next_date
        try:
            next_due_date = next_date(reminder)
        except (ValueError, OverflowError):
            return jsonify({'error': 'The next recurrence is outside the supported date range.'}), 400
        if next_due_date and reminder.recurrence_end and next_due_date > reminder.recurrence_end:
            next_due_date = None
        if next_due_date and reminder.due_mileage is not None:
            floor = max(reminder.due_mileage, reminder.vehicle.current_mileage or 0) if reminder.vehicle else reminder.due_mileage
            if reminder.repeat_mileage:
                next_due_mileage = floor + reminder.repeat_mileage
            else:
                try:
                    next_due_mileage = parse_optional_int((request.get_json(silent=True) or {}).get('next_due_mileage'))
                except InvalidFieldError as invalid:
                    payload, status = invalid_field_response(invalid)
                    return jsonify(payload), status
            if next_due_mileage is None or not floor < next_due_mileage <= 2147483647:
                return jsonify({'error': 'Set a mileage repeat interval in Edit reminder, or provide a new threshold above the current mileage.',
                                'message_key': 'reminderDelivery.mileageRequired', 'code': 'MILEAGE_RECURRENCE_REQUIRED',
                                'minimum_next_mileage': floor + 1}), 409
    reminder.completed = True
    reminder.completed_at = datetime.now(timezone.utc)

    if reminder.recurring and reminder.frequency and not Reminder.query.filter_by(completed_from_id=reminder.id).first():
        if next_due_date and (not reminder.recurrence_end or next_due_date <= reminder.recurrence_end):
            next_reminder = Reminder(
                completed_from_id=reminder.id,
                title=reminder.title,
                description=reminder.description,
                due_date=next_due_date,
                due_mileage=next_due_mileage,
                repeat_mileage=reminder.repeat_mileage,
                recurrence_anchor_date=reminder.recurrence_anchor_date or reminder.due_date,
                reminder_type=reminder.reminder_type,
                priority=reminder.priority,
                recurring=reminder.recurring,
                frequency=reminder.frequency,
                frequency_value=reminder.frequency_value,
                recurrence_end=reminder.recurrence_end,
                notify_days_before=reminder.notify_days_before,
                notify_email=reminder.notify_email,
                notify_push=reminder.notify_push,
                user_id=reminder.user_id,
                vehicle_id=reminder.vehicle_id
            )
            db.session.add(next_reminder)
    
    commit_mutation()
    
    return jsonify({
        'message': 'Reminder completed',
        'reminder': reminder.to_dict()
    })


@reminders_bp.route('/<int:reminder_id>/snooze', methods=['POST'])
@token_required
@mutation_endpoint(Reminder, 'reminder_id')
def snooze_reminder(current_user, reminder_id):
    """Snooze a reminder."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    data = request.get_json()
    try:
        days = parse_optional_int((data or {}).get('days', 1))
        if days is None or not 1 <= days <= 365:
            return jsonify({'error': 'Snooze days must be between 1 and 365.'}), 400
    except InvalidFieldError as invalid:
        payload, status = invalid_field_response(invalid)
        return jsonify(payload), status
    from app.services.reminder_delivery import delivery_state
    reminder.notification_state = delivery_state(reminder)
    reminder.snoozed_until = datetime.now(timezone.utc) + timedelta(days=days)
    
    commit_mutation()
    
    return jsonify({
        'message': f'Reminder snoozed for {days} days',
        'reminder': reminder.to_dict()
    })


@reminders_bp.route('/upcoming', methods=['GET'])
@token_required
def get_upcoming_reminders(current_user):
    """Get upcoming reminders."""
    days = request.args.get('days', 7, type=int)
    cutoff = utc_today() + timedelta(days=days)
    
    reminders = Reminder.query.filter(
        active_vehicle_condition(Reminder),
        Reminder.user_id == current_user.id,
        Reminder.completed == False,
        Reminder.dismissed == False,
        Reminder.due_date.isnot(None),
        Reminder.due_date <= cutoff
    ).order_by(Reminder.due_date.asc()).all()
    
    return jsonify({
        'reminders': [r.to_dict() for r in reminders]
    })


@reminders_bp.route('/overdue', methods=['GET'])
@token_required
def get_overdue_reminders(current_user):
    """Get overdue reminders."""
    reminders = Reminder.query.filter(
        active_vehicle_condition(Reminder),
        Reminder.user_id == current_user.id,
        Reminder.completed == False,
        Reminder.dismissed == False,
        Reminder.due_date.isnot(None),
        Reminder.due_date < utc_today()
    ).order_by(Reminder.due_date.asc()).all()
    
    return jsonify({
        'reminders': [r.to_dict() for r in reminders]
    })


@reminders_bp.route('/by-mileage', methods=['GET'])
@token_required
def get_mileage_reminders(current_user):
    """Get reminders due by mileage."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    
    if not vehicle_id:
        return jsonify({'error': 'Vehicle ID required'}), 400
    
    vehicle = Vehicle.query.filter_by(
        id=vehicle_id,
        user_id=current_user.id
    ).first()
    
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    threshold = request.args.get('threshold', 1000, type=int)
    
    reminders = Reminder.query.filter(
        active_vehicle_condition(Reminder),
        Reminder.user_id == current_user.id,
        Reminder.vehicle_id == vehicle_id,
        Reminder.completed == False,  # noqa: E712
        Reminder.dismissed == False,  # noqa: E712
        Reminder.due_mileage.isnot(None),
        Reminder.due_mileage <= vehicle.current_mileage + threshold
    ).order_by(Reminder.due_mileage.asc()).all()
    
    return jsonify({
        'reminders': [r.to_dict() for r in reminders],
        'current_mileage': vehicle.current_mileage
    })


@reminders_bp.route('/stats', methods=['GET'])
@token_required
def get_reminder_stats(current_user):
    """Get reminder statistics."""
    # M9: DB aggregation instead of loading every reminder into memory.
    # Boolean predicates use `.isnot(True)` so a NULL flag counts as "not set",
    # matching Python truthiness (`not r.completed` is True for False and None).
    # is_overdue → (not completed) AND (not dismissed) AND due_date < today,
    # with `today` in UTC exactly as the property computes it.
    uid = current_user.id
    today = datetime.now(timezone.utc).date()
    is_completed = Reminder.completed.is_(True)
    # Total/completed retain history; actionable counts follow the pending view.
    is_pending = and_(active_vehicle_condition(Reminder),
                      Reminder.completed.isnot(True), Reminder.dismissed.isnot(True))
    is_overdue = and_(is_pending, Reminder.due_date < today)

    completed_1 = func.coalesce(func.sum(case((is_completed, 1), else_=0)), 0)
    pending_1 = func.coalesce(func.sum(case((is_pending, 1), else_=0)), 0)

    total, completed, pending, overdue = (
        db.session.query(
            func.count(Reminder.id),
            completed_1,
            pending_1,
            func.coalesce(func.sum(case((is_overdue, 1), else_=0)), 0),
        )
        .filter(Reminder.user_id == uid)
        .one()
    )

    # By type — NULL/'' reminder_type → 'custom'. Per type: total, plus completed
    # (completed truthy) and pending (not completed AND not dismissed), matching
    # the original if/elif exactly.
    by_type = {}
    for rtype_raw, cnt, comp, pend in (
        db.session.query(
            Reminder.reminder_type,
            func.count(Reminder.id),
            completed_1,
            pending_1,
        )
        .filter(Reminder.user_id == uid)
        .group_by(Reminder.reminder_type)
        .all()
    ):
        rtype = rtype_raw or 'custom'
        if rtype not in by_type:
            by_type[rtype] = {'total': 0, 'pending': 0, 'completed': 0}
        by_type[rtype]['total'] += int(cnt)
        by_type[rtype]['completed'] += int(comp)
        by_type[rtype]['pending'] += int(pend)

    return jsonify({
        'total': int(total),
        'pending': int(pending),
        'completed': int(completed),
        'overdue': int(overdue),
        'by_type': by_type,
    })
