"""
GearCargo - Reminders Routes
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify, current_app

from app import db
from app.models import Vehicle, Reminder
from app.routes.auth import token_required

reminders_bp = Blueprint('reminders', __name__)


@reminders_bp.route('', methods=['GET'])
@token_required
def get_reminders(current_user):
    """Get reminders."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    status = request.args.get('status')  # upcoming, overdue, completed, pending, snoozed
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = Reminder.query.filter_by(user_id=current_user.id)
    
    if vehicle_id:
        query = query.filter(Reminder.vehicle_id == vehicle_id)
    
    today = date.today()
    
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
        return jsonify({'error': 'Title is required'}), 400
    
    reminder = Reminder(
        user_id=current_user.id,
        vehicle_id=vehicle_id,
        title=data['title'],
        description=data.get('description'),
        reminder_type=data.get('reminder_type', 'custom'),
        due_date=datetime.fromisoformat(data['due_date']).date() if data.get('due_date') else None,
        due_mileage=data.get('due_mileage'),
        priority=data.get('priority', 'medium'),
        completed=False,
        dismissed=False,
        # Recurrence
        recurring=data.get('is_recurring', False),
        frequency=data.get('recurrence_pattern'),
        frequency_value=data.get('recurrence_interval'),
        # Notifications
        notify_days_before=data.get('notify_days_before', 7),
        notify_push=data.get('notify_via_push', True),
        notify_email=data.get('notify_via_email', True),
        # Calendar
        calendar_sync=data.get('sync_to_calendar', False),
        # Translations
        title_translations=data.get('title_translations'),
        description_translations=data.get('description_translations'),
    )
    
    db.session.add(reminder)
    db.session.commit()
    
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
def update_reminder(current_user, reminder_id):
    """Update a reminder."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    data = request.get_json()
    
    allowed = ['title', 'description', 'reminder_type', 'due_date', 'due_mileage',
               'priority', 'status', 'is_recurring', 'recurrence_pattern',
               'recurrence_interval', 'recurrence_unit', 'notify_days_before',
               'notify_via_push', 'notify_via_email', 'sync_to_calendar',
               'title_translations', 'description_translations']
    
    for field in allowed:
        if field in data:
            if field == 'due_date' and data[field]:
                setattr(reminder, field, datetime.fromisoformat(data[field]).date())
            else:
                setattr(reminder, field, data[field])
    
    db.session.commit()
    
    return jsonify({
        'message': 'Reminder updated',
        'reminder': reminder.to_dict()
    })


@reminders_bp.route('/<int:reminder_id>', methods=['DELETE'])
@token_required
def delete_reminder(current_user, reminder_id):
    """Delete a reminder."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    db.session.delete(reminder)
    db.session.commit()
    
    return jsonify({'message': 'Reminder deleted'})


@reminders_bp.route('/<int:reminder_id>/complete', methods=['POST'])
@token_required
def complete_reminder(current_user, reminder_id):
    """Mark reminder as completed."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    data = request.get_json() or {}
    
    reminder.completed = True
    reminder.completed_at = datetime.utcnow()
    
    # Handle recurring reminder
    if reminder.recurring and reminder.frequency:
        # Create next occurrence
        from dateutil.relativedelta import relativedelta
        next_due_date = None
        freq_value = reminder.frequency_value or 1
        
        if reminder.frequency == 'daily':
            next_due_date = reminder.due_date + relativedelta(days=freq_value)
        elif reminder.frequency == 'weekly':
            next_due_date = reminder.due_date + relativedelta(weeks=freq_value)
        elif reminder.frequency == 'monthly':
            next_due_date = reminder.due_date + relativedelta(months=freq_value)
        elif reminder.frequency == 'yearly':
            next_due_date = reminder.due_date + relativedelta(years=freq_value)
        
        if next_due_date and (not reminder.recurrence_end or next_due_date <= reminder.recurrence_end):
            next_reminder = Reminder(
                title=reminder.title,
                description=reminder.description,
                due_date=next_due_date,
                due_mileage=reminder.due_mileage,
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
    
    db.session.commit()
    
    return jsonify({
        'message': 'Reminder completed',
        'reminder': reminder.to_dict()
    })


@reminders_bp.route('/<int:reminder_id>/snooze', methods=['POST'])
@token_required
def snooze_reminder(current_user, reminder_id):
    """Snooze a reminder."""
    reminder = Reminder.query.filter_by(
        id=reminder_id,
        user_id=current_user.id
    ).first()
    
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    data = request.get_json()
    days = data.get('days', 1)
    
    if reminder.due_date:
        reminder.due_date = reminder.due_date + timedelta(days=days)
    
    reminder.snoozed_until = datetime.utcnow() + timedelta(days=days)
    
    db.session.commit()
    
    return jsonify({
        'message': f'Reminder snoozed for {days} days',
        'reminder': reminder.to_dict()
    })


@reminders_bp.route('/upcoming', methods=['GET'])
@token_required
def get_upcoming_reminders(current_user):
    """Get upcoming reminders."""
    days = request.args.get('days', 7, type=int)
    cutoff = date.today() + timedelta(days=days)
    
    reminders = Reminder.query.filter(
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
        Reminder.user_id == current_user.id,
        Reminder.completed == False,
        Reminder.dismissed == False,
        Reminder.due_date.isnot(None),
        Reminder.due_date < date.today()
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
        Reminder.user_id == current_user.id,
        Reminder.vehicle_id == vehicle_id,
        Reminder.status == 'pending',
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
    reminders = Reminder.query.filter_by(user_id=current_user.id).all()
    
    completed = sum(1 for r in reminders if r.completed)
    pending = sum(1 for r in reminders if not r.completed and not r.dismissed)
    overdue = sum(1 for r in reminders if r.is_overdue)
    
    # By type
    by_type = {}
    for reminder in reminders:
        rtype = reminder.reminder_type or 'custom'
        if rtype not in by_type:
            by_type[rtype] = {'total': 0, 'pending': 0, 'completed': 0}
        by_type[rtype]['total'] += 1
        if reminder.completed:
            by_type[rtype]['completed'] += 1
        elif not reminder.dismissed:
            by_type[rtype]['pending'] += 1
    
    return jsonify({
        'total': len(reminders),
        'pending': pending,
        'completed': completed,
        'overdue': overdue,
        'by_type': by_type,
    })
