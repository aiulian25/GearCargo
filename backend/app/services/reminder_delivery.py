"""One logical push/email per date-or-mileage occurrence, with retryable claims.

An explicit reschedule or snooze starts a new delivery cycle. A transport's
positive acknowledgement means accepted, not read. A crash after acceptance
but before recording it can still cause a retry; SMTP has no idempotency key.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import update

from app import db
from app.models import Reminder, User
from app.services.restore_transaction import guarded_app_context
from app.services.vehicle_archive import active_vehicle_condition
from app.utils.timeutils import utc_naive_now
from app.utils.reminder_routes import reminder_path

CHANNELS = ('push', 'email')
LEASE = timedelta(minutes=30)


def naive_utc(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def occurrence_key(reminder):
    snooze = naive_utc(reminder.snoozed_until)
    fields = (reminder.due_date.isoformat() if reminder.due_date else '',
              str(reminder.due_mileage) if reminder.due_mileage is not None else '',
              snooze.isoformat() if snooze else '')
    return hashlib.sha256('|'.join(fields).encode()).hexdigest()


def delivery_state(reminder):
    key = occurrence_key(reminder)
    stored = reminder.notification_state
    if isinstance(stored, dict) and stored.get('occurrence') == key and isinstance(stored.get('channels'), dict):
        return deepcopy(stored)
    channels = {}
    # Old backups, like the schema migration, cannot prove which channel sent.
    # Do not reinterpret an unknown old attempt as a fresh unsent occurrence.
    if not stored and (reminder.last_notified_at or reminder.mileage_notified):
        channels = {channel: {'status': 'legacy_unknown'} for channel in CHANNELS}
    return {'version': 1, 'occurrence': key, 'channels': channels}


def eligibility(reminder, user, now, trigger):
    if (not user or not user.is_active or not user.notifications_enabled
            or reminder.completed or reminder.dismissed
            or (reminder.vehicle and (reminder.vehicle.archived or reminder.vehicle.user_id != user.id))):
        return False
    snooze = naive_utc(reminder.snoozed_until)
    if snooze and snooze > now:
        return False
    if reminder.reminder_type == 'workshop_preparation':
        from app.models import Appointment
        appointment = Appointment.query.filter_by(preparation_reminder_id=reminder.id, user_id=user.id).first()
        return bool(trigger != 'mileage' and appointment and appointment.status == 'confirmed' and not appointment.dropoff_at and snooze and now >= snooze)
    if trigger == 'mileage':
        vehicle = reminder.vehicle
        return bool(vehicle and vehicle.user_id == user.id and vehicle.current_mileage is not None
                    and reminder.due_mileage is not None and vehicle.current_mileage >= reminder.due_mileage)
    try:
        zone = ZoneInfo(user.timezone or 'UTC')
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    today = now.replace(tzinfo=timezone.utc).astimezone(zone).date()
    return reminder.due_date is not None and (reminder.due_date - today).days <= max(0, reminder.notify_days_before or 0)


def channel_enabled(reminder, user, channel, app):
    if channel == 'push':
        return reminder.notify_push
    return reminder.notify_email and user.email_reminder_alerts and app.config.get('MAIL_ENABLED')


def save_state(reminder, state, **values):
    """Portable atomic claim on SQLite/Postgres, including competing job workers."""
    changed = db.session.execute(update(Reminder).where(
        Reminder.id == reminder.id, Reminder.revision == reminder.revision).values(
            notification_state=state, revision=Reminder.revision + 1, **values),
        execution_options={'synchronize_session': False}).rowcount
    db.session.commit()
    return changed == 1


def claim(reminder_id, channel, trigger, now, app):
    for _ in range(10):
        reminder = db.session.get(Reminder, reminder_id, populate_existing=True)
        if not reminder:
            return None
        user = db.session.get(User, reminder.user_id, populate_existing=True)
        if not eligibility(reminder, user, now, trigger) or not channel_enabled(reminder, user, channel, app):
            return None
        state = delivery_state(reminder)
        previous = state['channels'].get(channel, {})
        if not isinstance(previous, dict):
            previous = {}
        if previous.get('status') in ('sent', 'legacy_unknown'):
            return None
        if previous.get('status') == 'sending' and (naive_utc(previous.get('lease_until')) or now) > now:
            return None
        if (naive_utc(previous.get('next_attempt_at')) or now) > now:
            return None
        token = str(uuid4())
        attempts = previous.get('attempts', 0)
        attempts = attempts if isinstance(attempts, int) and 0 <= attempts < 1000000 else 0
        state['channels'][channel] = {'status': 'sending', 'claim': token,
            'attempts': attempts + 1, 'attempted_at': now.isoformat(), 'lease_until': (now + LEASE).isoformat()}
        if save_state(reminder, state):
            return state['occurrence'], token
    return None


def finish(reminder_id, channel, claimed, accepted, now):
    for _ in range(10):
        reminder = db.session.get(Reminder, reminder_id, populate_existing=True)
        if not reminder:
            return
        state = delivery_state(reminder)
        outcome = state['channels'].get(channel, {})
        if state['occurrence'] != claimed[0] or outcome.get('claim') != claimed[1]:
            return
        outcome.pop('claim', None)
        outcome.pop('lease_until', None)
        outcome['status'] = 'sent' if accepted else 'retry'
        updates = {}
        if accepted:
            outcome['sent_at'] = now.isoformat()
            updates['last_notified_at'] = now
            if eligibility(reminder, db.session.get(User, reminder.user_id), now, 'mileage'):
                updates['mileage_notified'] = True
        else:
            minutes = min(1440, 15 * 2 ** min(outcome['attempts'] - 1, 7))
            outcome['next_attempt_at'] = (now + timedelta(minutes=minutes)).isoformat()
        if save_state(reminder, state, **updates):
            return


def send(reminder, user, channel, trigger):
    if channel == 'push':
        from app.routes.push import send_push_to_user
        body = reminder.description or ('Odometer threshold reached' if trigger == 'mileage' else 'This reminder is due soon or overdue')
        if trigger == 'mileage' and reminder.vehicle:
            body += f' — {reminder.due_mileage:,} {reminder.vehicle.distance_unit or "km"}'
        if reminder.vehicle:
            body += f' ({reminder.vehicle.name})'
        return send_push_to_user(user.id, f'Reminder: {reminder.title}', body,
            data={'type': 'reminder_mileage' if trigger == 'mileage' else 'reminder',
                  'reminder_id': reminder.id, 'vehicle_id': reminder.vehicle_id,
                  'url': reminder_path(reminder.id)}, tag=f'reminder-{reminder.id}') > 0
    from app.services.email_service import EmailService
    subtitle = (f'Odometer threshold: {reminder.due_mileage:,} {reminder.vehicle.distance_unit or "km"}'
                if trigger == 'mileage' else f'Due on {reminder.due_date.isoformat()}')
    return EmailService.send_alert_notification(user, [{'title': reminder.title, 'subtitle': subtitle,
        'details': reminder.description, 'vehicle': reminder.vehicle.name if reminder.vehicle else None,
        'severity': 'warning', 'due_date': reminder.due_date.isoformat() if reminder.due_date else None}], 'reminder') is True


def dispatch_reminders(app, trigger):
    with guarded_app_context(app):
        now = utc_naive_now()
        ids = db.session.query(Reminder.id).filter(active_vehicle_condition(Reminder),
            Reminder.completed.is_(False), Reminder.dismissed.is_(False)).all()
        for (reminder_id,) in ids:
            for channel in CHANNELS:
                claimed = None
                try:
                    claimed = claim(reminder_id, channel, trigger, now, app)
                    if not claimed:
                        continue
                    reminder = db.session.get(Reminder, reminder_id, populate_existing=True)
                    if not reminder:
                        continue
                    state = delivery_state(reminder)
                    if (state['occurrence'] != claimed[0]
                            or state['channels'].get(channel, {}).get('claim') != claimed[1]):
                        continue
                    user = db.session.get(User, reminder.user_id, populate_existing=True) if reminder else None
                    # Preferences/snooze may have changed while acquiring the claim.
                    accepted = bool(reminder and eligibility(reminder, user, now, trigger)
                                    and channel_enabled(reminder, user, channel, app)
                                    and send(reminder, user, channel, trigger))
                except Exception:
                    db.session.rollback()
                    app.logger.warning('Reminder %s %s delivery failed; eligible attempts remain retryable', reminder_id, channel)
                    if not claimed:
                        continue
                    accepted = False
                finish(reminder_id, channel, claimed, accepted, now)
