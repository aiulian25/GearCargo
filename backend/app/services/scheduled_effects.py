"""Commit scheduled transport intents with their domain changes, then deliver.

The reminder dispatcher retains GC-021's own per-channel receipt protocol.
Other scheduled push/email and external backup work uses this encrypted outbox.
"""
from datetime import timedelta
import hashlib
import json
from pathlib import Path

from sqlalchemy import select, update, or_

from app import db
from app.models.job_run import ScheduledEffect
from app.services.scheduler_ownership import active_run, database_now, insert_for
from app.utils.encryption import encrypt_field, decrypt_field


def effect_identity(kind, user_id, key):
    return hashlib.sha256(json.dumps([kind, user_id, key], sort_keys=True).encode()).hexdigest()


def generation_recorded(user_id, key):
    """A successor made by this occurrence must not become its next input."""
    run = active_run.get()
    if not run:
        return False
    return db.session.connection().execute(select(ScheduledEffect.id).where(
        ScheduledEffect.job_name == run.name, ScheduledEffect.occurrence_at == run.occurrence,
        ScheduledEffect.effect_key == effect_identity('generation', user_id, key))).first() is not None


def enqueue_effect(kind, user_id, key, payload):
    run = active_run.get()
    if not run or run.name == 'scheduled_deliveries':
        return False
    run.lock.check()
    connection = db.session.connection()
    now = database_now(connection)
    effect_key = effect_identity(kind, user_id, key)
    receipt = kind == 'generation'
    connection.execute(insert_for(connection, ScheduledEffect.__table__).values(
        user_id=user_id, job_name=run.name, occurrence_at=run.occurrence, effect_key=effect_key,
        kind=kind, payload=None if receipt else encrypt_field(json.dumps(payload)),
        status='recorded' if receipt else 'pending', attempts=0,
        next_attempt_at=now, created_at=now, completed_at=now if receipt else None).on_conflict_do_nothing(
            index_elements=['job_name', 'occurrence_at', 'effect_key']))
    return True


def deliver(effect, payload, user):
    if effect.kind == 'push':
        from app.routes.push import send_push_to_user
        if not user.notifications_enabled:
            return None
        vehicle_id = (payload.get('data') or {}).get('vehicle_id')
        if vehicle_id:
            from app.models import Vehicle
            if not Vehicle.query.filter_by(id=vehicle_id, user_id=user.id, archived=False).first():
                return None
        return send_push_to_user(user.id, **payload) > 0
    if effect.kind == 'email':
        from app.services.email_service import EmailService
        if not user.notifications_enabled or user.get_effective_notification_email() != payload['to']:
            return None
        preference = {'send_daily_alerts': 'daily_alerts_enabled', 'send_weekly_reports': 'weekly_report_enabled',
                      'send_monthly_reports': 'monthly_report_enabled'}.get(effect.job_name)
        if preference and not getattr(user, preference):
            return None
        return EmailService.send_email(**payload)
    if effect.kind == 'backup':
        from app.models import Backup, BackupSchedule
        from app.routes.backup import send_to_all_external_destinations
        backup = db.session.get(Backup, payload['backup_id'])
        schedule = db.session.get(BackupSchedule, payload['schedule_id'])
        if not backup or not schedule or backup.user_id != user.id or schedule.user_id != user.id:
            return None
        _, errors = send_to_all_external_destinations(Path(backup.filepath).read_bytes(), schedule, filename=backup.filename)
        if errors:
            backup.error_message = 'Scheduled external delivery requires retry'
        elif backup.error_message == 'Scheduled external delivery requires retry':
            backup.error_message = None
        return not errors
    raise ValueError('Unsupported scheduled delivery')


def process_scheduled_effects(app):
    from app.models import User
    from app.services.restore_transaction import guarded_app_context
    with guarded_app_context(app):
        now = database_now(db.session.connection())
        eligible = or_(ScheduledEffect.status.in_(['pending', 'retry']),
            (ScheduledEffect.status == 'sending') & (ScheduledEffect.lease_until <= now))
        ids = db.session.query(ScheduledEffect.id).filter(eligible,
            ScheduledEffect.next_attempt_at <= now).order_by(ScheduledEffect.next_attempt_at, ScheduledEffect.id).limit(50).all()
        db.session.commit()
        for (effect_id,) in ids:
            effect = db.session.get(ScheduledEffect, effect_id)
            if not effect:
                continue
            if effect.attempts >= 8:
                effect.status = 'failed'
                effect.last_error = 'delivery_retry_exhausted'
                effect.lease_until = None
                db.session.commit()
                continue
            effect.status = 'sending'
            effect.attempts += 1
            effect.lease_until = database_now(db.session.connection()) + timedelta(minutes=2)
            db.session.commit()
            try:
                user = db.session.get(User, effect.user_id)
                accepted = deliver(effect, json.loads(decrypt_field(effect.payload)), user) if user and user.is_active else None
            except Exception:
                db.session.rollback()
                effect = db.session.get(ScheduledEffect, effect_id)
                if not effect:
                    continue
                accepted = False
            now = database_now(db.session.connection())
            effect.lease_until = None
            if accepted is None or accepted:
                effect.status = 'cancelled' if accepted is None else 'sent'
                effect.completed_at = now
                effect.payload = None
                effect.last_error = None
            else:
                effect.status = 'failed' if effect.attempts >= 8 else 'retry'
                effect.next_attempt_at = now + timedelta(minutes=min(60, 2 ** min(effect.attempts - 1, 6)))
                effect.last_error = 'transport_unavailable'
            db.session.commit()


def delivery_status():
    from sqlalchemy import func
    return dict(db.session.query(ScheduledEffect.status, func.count(ScheduledEffect.id))
                .group_by(ScheduledEffect.status).all())


def register_delivery_cli(app):
    import click

    @app.cli.command('scheduler-retry-deliveries')
    def retry():
        """Retry failed deliveries; acknowledged effects are never replayed."""
        count = db.session.execute(update(ScheduledEffect).where(ScheduledEffect.status.in_(['retry', 'failed']))
            .values(status='pending', attempts=0, next_attempt_at=database_now(db.session.connection()), last_error=None)).rowcount
        db.session.commit()
        click.echo(f'Queued {count} scheduled deliveries.')
