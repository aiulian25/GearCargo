"""Workshop state, local-time validation and explicit resolution of selected work."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
import json
from app import db
from app.models import Reminder, Todo, ServiceEntry, PredictionAlert
from app.models.appointment import AppointmentTask
from app.utils.entryparse import InvalidFieldError
from app.utils.timeutils import utc_naive_now

TARGETS = {'reminder_id': Reminder, 'todo_id': Todo, 'service_id': ServiceEntry, 'prediction_id': PredictionAlert}


def invalid(field, key='invalid'):
    raise InvalidFieldError('appointments.' + key, 'Review the appointment details and linked work.', field)


def text(value, field, limit, required=False):
    if not required and value in (None, ''): return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit: invalid(field)
    return value.strip()


def zone_for(value):
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        invalid('time_zone')


def local_instant(value, zone, fold, field):
    try:
        local = datetime.strptime(value, '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        invalid(field)
    candidates = []
    for choice in (0, 1):
        aware = local.replace(tzinfo=zone, fold=choice)
        instant = aware.astimezone(timezone.utc)
        if instant.astimezone(zone).replace(tzinfo=None) == local:
            candidates.append((choice, instant))
    if not candidates: invalid(field, 'nonexistentTime')
    if len({v for _, v in candidates}) > 1 and (type(fold) is not int or fold not in (0, 1)):
        invalid(field, 'ambiguousTime')
    return next(v for f, v in candidates if f == (fold if fold in (0, 1) else 0)).replace(tzinfo=None)


def apply_details(record, data):
    for key, limit, required in [('title', 255, True), ('shop_name', 100, False), ('shop_contact', 255, False), ('notes', 10000, False)]:
        if key in data: setattr(record, key, text(data[key], key, limit, required))
    if not record.title: invalid('title')
    if any(k in data for k in ('start_local', 'end_local', 'time_zone', 'start_fold', 'end_fold')):
        zone = zone_for(data.get('time_zone'))
        record.time_zone = data['time_zone']
        record.start_at = local_instant(data.get('start_local'), zone, data.get('start_fold'), 'start_local')
        record.end_at = local_instant(data.get('end_local'), zone, data.get('end_fold'), 'end_local')
    if not record.start_at or not record.end_at or record.end_at <= record.start_at: invalid('end_local')
    if 'prepare_minutes' in data:
        value = data['prepare_minutes']
        if type(value) is not int or not 0 <= value <= 43200: invalid('prepare_minutes')
        record.prepare_minutes = value
    try:
        record.start_at - timedelta(minutes=record.prepare_minutes)
    except (OverflowError, TypeError):
        invalid('start_local')
    for field in ('notify_push', 'notify_email'):
        if field in data:
            if type(data[field]) is not bool: invalid(field)
            setattr(record, field, data[field])


def signature(target):
    # Portable content signature: local database IDs/revisions do not survive import.
    fields = ('title', 'description', 'due_date', 'due_mileage', 'next_due_date', 'next_due_mileage',
              'completed', 'dismissed', 'actioned', 'predicted_date', 'predicted_mileage', 'recurring',
              'frequency', 'frequency_value', 'repeat_mileage', 'recurrence_end', 'recurrence_anchor_date')
    values = {k: str(getattr(target, k)) for k in fields if hasattr(target, k)}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def set_tasks(record, rows):
    if not isinstance(rows, list) or len(rows) > 100: invalid('tasks')
    existing = {t.id: t for t in record.tasks}
    result = []; linked = set(); seen_ids = set()
    for row in rows:
        if not isinstance(row, dict): invalid('tasks')
        row_id = row.get('id')
        if row_id is not None:
            if type(row_id) is not int or row_id not in existing or row_id in seen_ids: invalid('tasks')
            seen_ids.add(row_id)
        task = existing.get(row_id)
        fields = [(f, row[f]) for f in TARGETS if row.get(f) is not None]
        if len(fields) > 1: invalid('tasks')
        target = None
        if fields:
            field, ident = fields[0]
            if type(ident) is not int or (field, ident) in linked: invalid('tasks')
            target = TARGETS[field].query.filter_by(id=ident, user_id=record.user_id, vehicle_id=record.vehicle_id).first()
            if not target or (field == 'reminder_id' and target.reminder_type == 'workshop_preparation'): invalid('tasks')
            linked.add((field, ident))
        unchanged_link = task is not None and all(getattr(task, f) == row.get(f) for f in TARGETS)
        if task is None: task = AppointmentTask(user_id=record.user_id, vehicle_id=record.vehicle_id)
        task.title = text(row.get('title'), 'tasks', 255, True)
        if type(row.get('done', False)) is not bool: invalid('tasks')
        if target and row.get('done', False): invalid('tasks')
        task.done = row.get('done', False)
        for f in TARGETS: setattr(task, f, row.get(f))
        if not unchanged_link:
            task.source_signature = signature(target) if target else None
        result.append(task)
    record.tasks = result


def sync_preparation(record):
    reminder = db.session.get(Reminder, record.preparation_reminder_id) if record.preparation_reminder_id else None
    if reminder is None:
        reminder = Reminder(user_id=record.user_id, vehicle_id=record.vehicle_id, reminder_type='workshop_preparation')
        db.session.add(reminder)
    when = record.start_at - timedelta(minutes=record.prepare_minutes)
    reminder.title = record.title
    reminder.description = record.shop_name
    reminder.reminder_type = 'workshop_preparation'
    reminder.recurring = False
    reminder.due_mileage = None
    reminder.due_date = when.replace(tzinfo=timezone.utc).astimezone(zone_for(record.time_zone)).date()
    if reminder.snoozed_until != when:
        reminder.last_notified_at = None; reminder.notification_state = {}; reminder.mileage_notified = False
    reminder.snoozed_until = when
    reminder.notify_days_before = 0
    reminder.notify_push, reminder.notify_email = record.notify_push, record.notify_email
    reminder.dismissed = record.status != 'confirmed' or record.dropoff_at is not None
    reminder.completed = record.status == 'completed'
    db.session.flush()
    record.preparation_reminder_id = reminder.id


def resolve_task(task):
    if task.source_signature and not any(getattr(task, field) is not None for field in TARGETS):
        invalid('tasks', 'changedTask')
    for field, model in TARGETS.items():
        ident = getattr(task, field)
        if ident is None: continue
        target = model.query.filter_by(id=ident, user_id=task.user_id, vehicle_id=task.vehicle_id).with_for_update(of=model.__mapper__.base_mapper.local_table).first()
        if not target or task.source_signature != signature(target): invalid('tasks', 'changedTask')
        if field in ('reminder_id', 'todo_id'):
            if not target.completed:
                if target.recurring and target.frequency:
                    if field == 'reminder_id':
                        from app.services.reminder_recurrence import next_date
                        due = next_date(target)
                        if due and target.recurrence_end and due > target.recurrence_end: due = None
                        mileage = None
                        if due and target.due_mileage is not None:
                            if not target.repeat_mileage: invalid('tasks', 'recurringMileage')
                            mileage = max(target.due_mileage, target.vehicle.current_mileage or 0) + target.repeat_mileage
                            if mileage > 2147483647: invalid('tasks')
                        extra = dict(due_mileage=mileage, repeat_mileage=target.repeat_mileage,
                            recurrence_anchor_date=target.recurrence_anchor_date or target.due_date,
                            recurrence_end=target.recurrence_end, reminder_type=target.reminder_type,
                            notify_days_before=target.notify_days_before, notify_email=target.notify_email, notify_push=target.notify_push)
                    else:
                        from dateutil.relativedelta import relativedelta
                        step = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}.get(target.frequency)
                        due = target.due_date + relativedelta(**{step: target.frequency_value or 1}) if step and target.due_date else None
                        extra = {}
                    if due and not model.query.filter_by(completed_from_id=target.id).first():
                        db.session.add(model(user_id=target.user_id, vehicle_id=target.vehicle_id,
                            completed_from_id=target.id, title=target.title, description=target.description,
                            due_date=due, priority=target.priority, recurring=True, frequency=target.frequency,
                            frequency_value=target.frequency_value, **extra))
                target.mark_complete()
        elif field == 'service_id':
            target.next_due_date = None; target.next_due_mileage = None
        else:
            target.actioned = True; target.actioned_at = utc_naive_now()
    task.done = True


def validate_backup_appointments(records):
    """Preflight owner-local graph and timezone/state invariants before restore."""
    from app.services.backup_schema import BackupSchemaError, ENTRY_COLLECTIONS
    try:
        appointments = {r['id']: r for r in records['appointments']}
        targets = {f: {r['id']: r for r in records[k]} for f, k in {
            'reminder_id': 'reminders', 'todo_id': 'todos', 'service_id': 'service_entries', 'prediction_id': 'predictions'}.items()}
        entries = {r['id']: r for k in ENTRY_COLLECTIONS for r in records[k]}
        eligible_entries = {r['id'] for k in ('service_entries', 'repair_entries') for r in records[k]}
        reminder_ids = set(); expense_ids = set()
        for row in appointments.values():
            zone_for(row['time_zone']); text(row['title'], 'title', 255, True)
            text(row['shop_name'], 'shop_name', 100); text(row['shop_contact'], 'shop_contact', 255); text(row['notes'], 'notes', 10000)
            if row['status'] not in ('requested', 'confirmed', 'completed', 'cancelled') or row['end_at'] <= row['start_at']: invalid('appointments')
            if not 0 <= row['prepare_minutes'] <= 43200: invalid('prepare_minutes')
            if row['status'] in ('confirmed', 'completed') and row['confirmed_at'] is None: invalid('status')
            if row['status'] == 'completed' and (row['dropoff_at'] is None or row['pickup_at'] is None): invalid('status')
            if row['pickup_at'] and (row['dropoff_at'] is None or row['pickup_at'] < row['dropoff_at']): invalid('pickup_at')
            rid = row['preparation_reminder_id']
            if rid is not None:
                reminder = targets['reminder_id'][rid]
                if rid in reminder_ids or reminder['vehicle_id'] != row['vehicle_id'] or reminder['reminder_type'] != 'workshop_preparation': invalid('preparation_reminder_id')
                reminder_ids.add(rid)
        for row in records['appointment_tasks']:
            appointment = appointments[row['appointment_id']]
            if appointment['vehicle_id'] != row['vehicle_id']: invalid('vehicle_id')
            text(row['title'], 'title', 255, True)
            linked = [f for f in TARGETS if row[f] is not None]
            if len(linked) > 1: invalid('tasks')
            for field in linked:
                if targets[field][row[field]]['vehicle_id'] != row['vehicle_id']: invalid(field)
                if field == 'reminder_id' and targets[field][row[field]]['reminder_type'] == 'workshop_preparation': invalid(field)
        for row in records['appointment_expenses']:
            appointment = appointments[row['appointment_id']]
            if appointment['status'] != 'completed' or appointment['vehicle_id'] != row['vehicle_id']: invalid('appointment_id')
            if row['entry_id'] not in eligible_entries or row['entry_id'] in expense_ids or entries[row['entry_id']]['vehicle_id'] != row['vehicle_id']: invalid('entry_id')
            expense_ids.add(row['entry_id'])
    except (InvalidFieldError, KeyError, TypeError, AttributeError):
        raise BackupSchemaError('Workshop appointment details or links are inconsistent.', 'appointments') from None
